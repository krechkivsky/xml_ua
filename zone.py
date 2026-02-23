

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
from qgis.PyQt.QtWidgets import QMessageBox
from lxml import etree

from .common import ensure_object_layer_fields


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
            return QgsPolygon()  # Повертаємо порожній полігон

        exterior_ring = QgsLineString(
            [QgsPointXY(p.y(), p.x()) for p in coordinates])

        polygon = QgsPolygon(exterior_ring)
        return polygon

    def add_zone_layer(self):
        """Створює та заповнює шар 'Кадастрова зона'."""
        self.layer_name = "Кадастрова зона"
        self.layer = QgsVectorLayer(
            f"MultiPolygon?crs={self.crs_epsg}", self.layer_name, "memory")

        self.layer.setCustomProperty("skip_save_dialog", True)

        if not self.layer.isValid():
            QMessageBox.critical(
                None, "xml_ua", "Виникла помилка при створенні шару зон.")
            return None

        self.layer.loadNamedStyle(os.path.join(
            self.plugin_dir, "templates", "zone.qml"))
        provider = self.layer.dataProvider()
        ensure_object_layer_fields(self.layer)

        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.root.getroottree())
        except Exception:
            processor = None

        for zone_element in self.root.findall(".//CadastralZoneInfo"):

            parcel_metric_info = self.root.find(".//ParcelMetricInfo")
            if parcel_metric_info is None:

                external_coords = []
                internal_coords_list = []
                externals_lines = None
                internals_lines_list = []
            else:

                externals_lines_list = parcel_metric_info.findall(".//Externals/Boundary/Lines")
                externals_lines = externals_lines_list[0] if externals_lines_list else None
                external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

                internals_lines_list = parcel_metric_info.findall(".//Internals/Boundary/Lines")
                internal_coords_list = [
                    self.lines_to_coords(lines_el) for lines_el in internals_lines_list if lines_el is not None
                ]

                zone_externals = zone_element.find(
                    "Externals")  # Шукаємо існуючий
                if zone_externals is not None:

                    zone_element.remove(zone_externals)

                zone_externals = etree.Element("Externals")  # Створюємо новий

                zone_number_element = zone_element.find("CadastralZoneNumber")
                if zone_number_element is not None:

                    zone_number_element.addnext(zone_externals)
                else:

                    zone_element.append(zone_externals)

                parcel_externals = parcel_metric_info.find("Externals")
                if parcel_externals is not None:

                    # Copy all boundaries (+ optional Internals) from ParcelMetricInfo/Externals
                    for child in list(zone_externals):
                        zone_externals.remove(child)
                    for child in parcel_externals:
                        zone_externals.append(etree.fromstring(etree.tostring(child)))

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords_list and not polygon.isEmpty():
                for internal_coords in internal_coords_list:
                    if not internal_coords:
                        continue
                    interior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in internal_coords])
                    polygon.addInteriorRing(interior_ring)

            feature = QgsFeature(self.layer.fields())

            feature.setGeometry(QgsGeometry(polygon))
            object_shape = ""
            if processor:
                try:
                    exterior_shape = processor._get_polyline_object_shape(externals_lines) if externals_lines is not None else ""
                    interior_shapes = []
                    for lines_el in internals_lines_list:
                        try:
                            interior_shapes.append(processor._get_polyline_object_shape(lines_el))
                        except Exception:
                            continue
                    object_shape = "|".join([s for s in ([exterior_shape] + interior_shapes) if s])
                except Exception:
                    object_shape = ""

            feature.setAttributes([1, object_shape])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        if hasattr(self, 'xml_ua_layers'):
            self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
