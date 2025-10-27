# -*- coding: utf-8 -*-
# leases.py

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

from .common import logFile, insert_element_in_order
from .common import log_msg

class Leases:
    """Клас для обробки даних про оренду з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з орендою.

        Args:
            root: Кореневий елемент XML-дерева.
            crs_epsg (str): EPSG-код системи координат.
            group (QgsLayerTreeGroup): Група шарів у QGIS.
            plugin_dir (str): Шлях до директорії плагіна.
            lines_to_coords_func (function): Функція для перетворення ліній у координати.
            xml_ua_layers_instance: Екземпляр класу xmlUaLayers для доступу до його методів.
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
            return QgsPolygon()
        # Координати в XML (X, Y) відповідають (Y, X) в QGIS
        line_string = QgsLineString([QgsPointXY(p.y(), p.x()) for p in coordinates])
        polygon = QgsPolygon(line_string)
        return polygon

    def redraw_leases_layer(self, layer):
        """Очищує та заповнює існуючий шар 'Оренда'."""
        provider = layer.dataProvider()
        layer.startEditing()
        layer.deleteFeatures(layer.allFeatureIds())

        leases_parent = self.root.find(".//ParcelInfo/Leases")
        if leases_parent is None:
            layer.commitChanges()
            return

        for lease in leases_parent.findall(".//LeaseInfo"):
            lease_duration = lease.findtext(".//LeaseAgreement/LeaseTerm/LeaseDuration")
            registration_date = lease.findtext(".//LeaseAgreement/RegistrationDate")
            area_element = lease.find(".//LeaseAgreement/Area")
            area = float(area_element.text) if area_element is not None and area_element.text else None

            externals_lines = lease.find(".//Externals/Boundary/Lines")
            external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

            internals_lines = lease.find(".//Internals/Boundary/Lines")
            internal_coords = self.lines_to_coords(internals_lines) if internals_lines is not None else []

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                polygon.addInteriorRing(self._coord_to_polygon(internal_coords).exteriorRing())

            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([lease_duration, registration_date, area])
            provider.addFeature(feature)
        layer.commitChanges()

    def add_leases_layer(self):
        """Створює та заповнює шар 'Оренда'."""
        # --- Зміни: Знаходимо або створюємо Leases у правильному місці ---
        parcel_info = self.root.find(".//ParcelInfo")
        leases_parent = parcel_info.find("Leases")
        if leases_parent is None:
            # Якщо розділу немає, ми не створюємо його, а просто виходимо,
            # оскільки це означає, що даних про оренду немає.
            # Якщо в майбутньому знадобиться додавати оренду,
            # тут потрібно буде створити елемент і вставити його за допомогою insert_element_in_order
            #log_msg(logFile, "Розділ 'Leases' відсутній. Шар 'Оренда' не буде створено.")
            return None

        layer_name = "Оренда"
        self.layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")
        # --- Початок змін: Встановлення прапорця тимчасового шару ---
        # Повідомляємо QGIS, що цей шар не потрібно зберігати при закритті проекту.
        self.layer.setCustomProperty("skip_save_dialog", True)
        # --- Кінець змін ---
        self.layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "lease.qml"))
        provider = self.layer.dataProvider()

        # --- Початок змін: Додавання поля object_shape ---
        fields = [
            QgsField("LeaseDuration", QVariant.String),
            QgsField("RegistrationDate", QVariant.String),
            QgsField("Area", QVariant.Double),
            QgsField("object_shape", QVariant.String),
        ]
        provider.addAttributes(fields)
        self.layer.updateFields()

        for lease in leases_parent.findall(".//LeaseInfo"):
            lease_duration = lease.findtext(".//LeaseAgreement/LeaseTerm/LeaseDuration")
            registration_date = lease.findtext(".//LeaseAgreement/RegistrationDate")

            # --- Початок змін: Генерація object_shape ---
            try:
                from .topology import GeometryProcessor
                processor = GeometryProcessor(self.root.getroottree())
            except Exception as e:
                log_msg(logFile, f"Не вдалося створити GeometryProcessor в Leases: {e}")
                processor = None
            # --- Кінець змін ---

            area_element = lease.find(".//LeaseAgreement/Area")
            area = float(area_element.text) if area_element is not None and area_element.text else None

            externals_element = lease.find(".//Externals")
            if externals_element is None:
                #log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Для оренди від '{registration_date}' відсутній обов'язковий розділ 'Externals'. Створено порожній об'єкт.")
                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

            internals_lines = lease.find(".//Internals/Boundary/Lines")
            internal_coords = self.lines_to_coords(internals_lines) if internals_lines is not None else []

            # --- Початок змін: Генерація та збереження object_shape ---
            object_shape = ""
            if processor and externals_element is not None:
                exterior_shape = processor._get_polyline_object_shape(externals_element.find("Boundary/Lines"))
                interior_shapes = []
                internals_container = externals_element.find("Internals")
                if internals_container is not None:
                    interior_shapes = [processor._get_polyline_object_shape(internal.find("Boundary/Lines")) for internal in internals_container.findall("Boundary")]
                object_shape = "|".join([exterior_shape] + interior_shapes)
                log_msg(logFile, f"Додано Оренду '{object_shape}'")
            # --- Кінець змін ---

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                polygon.addInteriorRing(self._coord_to_polygon(internal_coords).exteriorRing())

            feature = QgsFeature(self.layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([lease_duration, registration_date, area, object_shape])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))
            # #log_msg(logFile, f"Встановлено custom property на шар '{self.layer.name()}' з ID xml_data: {id(self.xml_data)}")

        return self.layer