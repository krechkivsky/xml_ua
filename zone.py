# -*- coding: utf-8 -*-
# zone.py

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

class CadastralZoneInfo:
    """Клас для обробки кадастрової зони з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з кадастровою зоною.

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

    def _coord_to_polygon(self, coordinates):
        """Формує полігон із заданого списку координат."""
        if not coordinates:
            return QgsPolygon() # Повертаємо порожній полігон
        
        # Створюємо QgsLineString для зовнішнього кільця.
        exterior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in coordinates])
        # Передаємо кільце в конструктор QgsPolygon. Володіння кільцем переходить до полігону.
        polygon = QgsPolygon(exterior_ring)
        return polygon

    def add_zone_layer(self):
        """Створює та заповнює шар 'Кадастрова зона'."""
        self.layer_name = "Кадастрова зона"
        self.layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", self.layer_name, "memory")
        # --- Початок змін: Встановлення прапорця тимчасового шару ---
        # Повідомляємо QGIS, що цей шар не потрібно зберігати при закритті проекту.
        self.layer.setCustomProperty("skip_save_dialog", True)
        # --- Кінець змін ---

        if not self.layer.isValid():
            QMessageBox.critical(None, "xml_ua", "Виникла помилка при створенні шару зон.")
            return None

        self.layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "zone.qml"))
        provider = self.layer.dataProvider()
        provider.addAttributes([QgsField("CadastralZoneNumber", QVariant.String)])
        self.layer.updateFields()

        zone_number = self.root.findtext(".//CadastralZoneInfo/CadastralZoneNumber")

        for zone_element in self.root.findall(".//CadastralZoneInfo"):
            # Використовуємо геометрію з ParcelMetricInfo, оскільки вона тотожна
            parcel_metric_info = self.root.find(".//ParcelMetricInfo")
            if parcel_metric_info is None:
                #log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Не знайдено ParcelMetricInfo для створення геометрії зони '{zone_number}'.")
                external_coords = []
                internal_coords = []
            else:
                # Читаємо геометрію з ділянки
                externals_lines = parcel_metric_info.find(".//Externals/Boundary/Lines")
                external_coords = self.lines_to_coords(externals_lines, context='open') if externals_lines is not None else []

                internals_lines = parcel_metric_info.find(".//Internals/Boundary/Lines")
                internal_coords = self.lines_to_coords(internals_lines, context='open') if internals_lines is not None else []

                # Забезпечуємо наявність та копіюємо геометрію в розділ зони
                # --- Початок змін: Вставка Externals у правильну позицію ---
                zone_externals = zone_element.find("Externals") # Шукаємо існуючий
                if zone_externals is not None:
                    zone_element.remove(zone_externals) # Видаляємо, щоб перевставити
                
                zone_externals = etree.Element("Externals") # Створюємо новий

                zone_number_element = zone_element.find("CadastralZoneNumber")
                if zone_number_element is not None:
                    zone_number_element.addnext(zone_externals) # Вставляємо після CadastralZoneNumber
                else:
                    zone_element.append(zone_externals) # Якщо CadastralZoneNumber не знайдено, додаємо в кінець
                # Копіюємо Externals
                parcel_externals = parcel_metric_info.find("Externals")
                if parcel_externals is not None:
                    # Видаляємо старий Boundary, якщо він є, і копіюємо новий
                    old_boundary = zone_externals.find("Boundary")
                    if old_boundary is not None:
                        zone_externals.remove(old_boundary)
                    zone_externals.append(etree.fromstring(etree.tostring(parcel_externals.find("Boundary"))))
                # --- Кінець змін ---

            # #log_msg(logFile, f"Створення полігону для зони '{zone_number}'. Зовнішніх контурів: {len(external_coords)}, Внутрішніх: {len(internal_coords)}")
            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                # Створюємо внутрішнє кільце як QgsLineString
                #log_msg(logFile, "Додавання внутрішнього кільця до зони.")
                interior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in internal_coords])
                # Додаємо його до геометрії полігону
                if not polygon.isEmpty():
                    polygon.addInteriorRing(interior_ring)

            feature = QgsFeature(self.layer.fields())
            # #log_msg(logFile, f"Геометрія зони перед додаванням: {polygon.asWkt()}")
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([zone_number])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        if hasattr(self, 'xml_ua_layers'):
            self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))
            # #log_msg(logFile, f"Встановлено custom property на шар '{self.layer.name()}' з ID xml_data: {id(self.xml_data)}")

        return self.layer