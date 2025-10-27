# -*- coding: utf-8 -*-
# quarters.py

import os
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPolygon,
    QgsLineString,
    QgsPointXY,
    QgsProject
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from lxml import etree

from .common import logFile
from .common import log_msg


class CadastralQuarters:
    """Клас для обробки кадастрових кварталів з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з кадастровими кварталами.

        Args:
            root: Кореневий елемент XML-дерева.
            crs_epsg (str): EPSG-код системи координат.
            group (QgsLayerTreeGroup): Група шарів у QGIS.
            plugin_dir (str): Шлях до директорії плагіна.
            lines_to_coords_func (function): Функція для перетворення ліній у координати.
        """
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.lines_to_coords = lines_to_coords_func
        self.xml_ua_layers = xml_ua_layers_instance
        self.xml_data = xml_data

    def _get_full_name(self, person_element):
        """Формує повне ім'я особи з XML-елемента."""
        if person_element is None:
            return ""
        last_name = person_element.findtext("LastName", "")
        first_name = person_element.findtext("FirstName", "")
        middle_name = person_element.findtext("MiddleName", "")
        return f"{last_name} {first_name} {middle_name}".strip()

    def _coord_to_polygon(self, coordinates):
        """Формує полігон із заданого списку координат."""
        if not coordinates:
            return QgsPolygon() # Повертаємо порожній полігон
        # Створюємо QgsLineString для зовнішнього кільця.
        exterior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in coordinates])
        # Передаємо кільце в конструктор QgsPolygon. Володіння кільцем переходить до полігону.
        polygon = QgsPolygon(exterior_ring)
        return polygon

    def add_quarter_layer(self):
        """Створює та заповнює шар 'Кадастровий квартал'."""
        self.layer_name = "Кадастровий квартал"
        self.layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", self.layer_name, "memory")
        # --- Початок змін: Встановлення прапорця тимчасового шару ---
        # Повідомляємо QGIS, що цей шар не потрібно зберігати при закритті проекту.
        self.layer.setCustomProperty("skip_save_dialog", True)
        # --- Кінець змін ---

        if not self.layer.isValid():
            QMessageBox.critical(None, "xml_ua", "Виникла помилка при створенні шару кварталів.")
            return None

        self.layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "quarter.qml"))
        provider = self.layer.dataProvider()
        provider.addAttributes([
            QgsField("CadastralQuarterNumber", QVariant.String),
            QgsField("LocalAuthorityHead", QVariant.String),
            QgsField("DKZRHead", QVariant.String)
        ])
        self.layer.updateFields()

        for quarter_element in self.root.findall(".//CadastralQuarterInfo"):
            quarter_number = quarter_element.findtext("CadastralQuarterNumber")
            auth_head_full_name = self._get_full_name(quarter_element.find("RegionalContacts/LocalAuthorityHead"))
            dkzr_head_full_name = self._get_full_name(quarter_element.find("RegionalContacts/DKZRHead"))

            # Використовуємо геометрію з ParcelMetricInfo, оскільки вона тотожна
            parcel_metric_info = self.root.find(".//ParcelMetricInfo")
            if parcel_metric_info is None:
                #log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Не знайдено ParcelMetricInfo для створення геометрії кварталу '{quarter_number}'.")
                external_coords = []
                internal_coords = []
            else:
                # Читаємо геометрію з ділянки
                externals_lines = parcel_metric_info.find(".//Externals/Boundary/Lines")
                external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []
                
                internals_lines = parcel_metric_info.find(".//Internals/Boundary/Lines")
                internal_coords = self.lines_to_coords(internals_lines) if internals_lines is not None else []

                # Забезпечуємо наявність та копіюємо геометрію в розділ кварталу
                # --- Початок змін: Вставка Externals у правильну позицію ---
                quarter_externals = quarter_element.find("Externals")
                if quarter_externals is not None:
                    quarter_element.remove(quarter_externals) # Видаляємо, щоб перевставити
                
                quarter_externals = etree.Element("Externals") # Створюємо новий

                regional_contacts_element = quarter_element.find("RegionalContacts")
                if regional_contacts_element is not None:
                    regional_contacts_element.addnext(quarter_externals) # Вставляємо після RegionalContacts
                else:
                    quarter_element.append(quarter_externals) # Якщо RegionalContacts не знайдено, додаємо в кінець
                # Копіюємо Externals
                parcel_externals = parcel_metric_info.find("Externals")
                if parcel_externals is not None:
                    # Видаляємо старий Boundary, якщо він є, і копіюємо новий
                    old_boundary = quarter_externals.find("Boundary")
                    if old_boundary is not None:
                        quarter_externals.remove(old_boundary)
                    quarter_externals.append(etree.fromstring(etree.tostring(parcel_externals.find("Boundary"))))
                # --- Кінець змін ---

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                polygon.addInteriorRing(self._coord_to_polygon(internal_coords).exteriorRing())

            feature = QgsFeature(self.layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([quarter_number, auth_head_full_name, dkzr_head_full_name])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        if hasattr(self, 'xml_ua_layers'):
            self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))
            # #log_msg(logFile, f"Встановлено custom property на шар '{self.layer.name()}' з ID xml_data: {id(self.xml_data)}")

        return self.layer