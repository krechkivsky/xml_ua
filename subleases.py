# -*- coding: utf-8 -*-
# subleases.py

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

class Subleases:
    """Клас для обробки даних про суборенду з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з суборендою.

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

    def redraw_subleases_layer(self, layer):
        """Очищує та заповнює існуючий шар 'Суборенда'."""
        provider = layer.dataProvider()
        layer.startEditing()
        layer.deleteFeatures(layer.allFeatureIds())

        subleases_parent = self.root.find(".//ParcelInfo/Subleases")
        if subleases_parent is None:
            layer.commitChanges()
            return

        for sublease in subleases_parent.findall(".//SubleaseInfo"):
            registration_date = sublease.findtext(".//SubleaseAgreement/RegistrationDate")
            area_element = sublease.find(".//SubleaseAgreement/Area")
            area = float(area_element.text) if area_element is not None and area_element.text else None

            externals_lines = sublease.find(".//Externals/Boundary/Lines")
            external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

            internal_coords_list = [self.lines_to_coords(b.find('Lines')) for b in sublease.findall(".//Internals/Boundary") if b.find('Lines') is not None]

            polygon = self._coord_to_polygon(external_coords)
            if not polygon.isEmpty():
                for internal_coords in internal_coords_list:
                    if internal_coords:
                        # --- Початок змін: Створення QgsLineString безпосередньо ---
                        # Створюємо QgsLineString напряму, щоб уникнути проблем з володінням пам'яттю
                        # тимчасового QgsPolygon, що викликало крах QGIS.
                        interior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in internal_coords])
                        polygon.addInteriorRing(interior_ring)
                        # --- Кінець змін ---

            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([registration_date, area])
            provider.addFeature(feature)
        layer.commitChanges()

    def add_subleases_layer(self):
        """Створює та заповнює шар 'Суборенда'."""
        parcel_info = self.root.find(".//ParcelInfo")
        subleases_parent = parcel_info.find("Subleases")
        if subleases_parent is None:
            # Аналогічно до оренди, виходимо, якщо розділу немає
            #log_msg(logFile,"Розділ 'Subleases' відсутній. Шар 'Суборенда' не буде створено.")
            return None

        layer_name = "Суборенда"
        self.layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")
        self.layer.setCustomProperty("skip_save_dialog", True)
        self.layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "sublease.qml"))
        provider = self.layer.dataProvider()

        # --- Початок змін: Додавання поля object_shape ---
        fields = [
            QgsField("RegistrationDate", QVariant.String),
            QgsField("Area", QVariant.Double),
            QgsField("object_shape", QVariant.String),
        ]
        provider.addAttributes(fields)
        self.layer.updateFields()

        for sublease in subleases_parent.findall(".//SubleaseInfo"):
            registration_date = sublease.findtext(".//SubleaseAgreement/RegistrationDate")

            # --- Початок змін: Генерація object_shape ---
            try:
                from .topology import GeometryProcessor
                processor = GeometryProcessor(self.root.getroottree())
            except Exception as e:
                log_msg(logFile, f"Не вдалося створити GeometryProcessor в Subleases: {e}")
                processor = None
            # --- Кінець змін ---

            area_element = sublease.find(".//Area")
            area = float(area_element.text) if area_element is not None and area_element.text else None

            externals_element = sublease.find(".//Externals")
            if externals_element is None:
                #log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Для суборенди від '{registration_date}' відсутній обов'язковий розділ 'Externals'. Створено порожній об'єкт.")
                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(externals_lines, context='open') if externals_lines is not None else []

            internal_coords_list = [self.lines_to_coords(b.find('Lines'), context='open') for b in sublease.findall(".//Internals/Boundary") if b.find('Lines') is not None]

            # --- Початок змін: Генерація та збереження object_shape ---
            object_shape = ""
            if processor and externals_element is not None:
                exterior_shape = processor._get_polyline_object_shape(externals_element.find("Boundary/Lines"))
                interior_shapes = []
                internals_container = externals_element.find("Internals")
                if internals_container is not None:
                    interior_shapes = [processor._get_polyline_object_shape(internal.find("Boundary/Lines")) for internal in internals_container.findall("Boundary")]
                object_shape = "|".join([exterior_shape] + interior_shapes)
                log_msg(logFile, f"Додано Суборенду: '{object_shape}'")
            # --- Кінець змін ---

            polygon = self._coord_to_polygon(external_coords)
            if not polygon.isEmpty():
                for internal_coords in internal_coords_list:
                    if internal_coords:
                        # --- Початок змін: Створення QgsLineString безпосередньо ---
                        # Створюємо QgsLineString напряму, щоб уникнути проблем з володінням пам'яттю
                        # тимчасового QgsPolygon, що викликало крах QGIS.
                        interior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in internal_coords])
                        polygon.addInteriorRing(interior_ring)
                        # --- Кінець змін ---

            feature = QgsFeature(self.layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([registration_date, area, object_shape])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))
            # #log_msg(logFile, f"Встановлено custom property на шар '{self.layer.name()}' з ID xml_data: {id(self.xml_data)}")

        return self.layer