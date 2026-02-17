

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
from .common import ensure_object_layer_fields, log_msg


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
            return QgsPolygon()  # Повертаємо порожній полігон

        exterior_ring = QgsLineString(
            [QgsPointXY(p.y(), p.x()) for p in coordinates])

        polygon = QgsPolygon(exterior_ring)
        return polygon

    def add_quarter_layer(self):
        """Створює та заповнює шар 'Кадастровий квартал'."""
        self.layer_name = "Кадастровий квартал"
        self.layer = QgsVectorLayer(
            f"MultiPolygon?crs={self.crs_epsg}", self.layer_name, "memory")

        self.layer.setCustomProperty("skip_save_dialog", True)

        if not self.layer.isValid():
            QMessageBox.critical(
                None, "xml_ua", "Виникла помилка при створенні шару кварталів.")
            return None

        self.layer.loadNamedStyle(os.path.join(
            self.plugin_dir, "templates", "quarter.qml"))
        provider = self.layer.dataProvider()
        ensure_object_layer_fields(self.layer)

        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.root.getroottree())
        except Exception:
            processor = None

        object_id = 0

        for quarter_element in self.root.findall(".//CadastralQuarterInfo"):
            object_id += 1

            parcel_metric_info = self.root.find(".//ParcelMetricInfo")
            if parcel_metric_info is None:

                external_coords = []
                internal_coords = []
                externals_lines = None
                internals_lines = None
            else:

                externals_lines = parcel_metric_info.find(
                    ".//Externals/Boundary/Lines")
                external_coords = self.lines_to_coords(
                    externals_lines) if externals_lines is not None else []

                internals_lines = parcel_metric_info.find(
                    ".//Internals/Boundary/Lines")
                internal_coords = self.lines_to_coords(
                    internals_lines) if internals_lines is not None else []

                quarter_externals = quarter_element.find("Externals")
                if quarter_externals is not None:

                    quarter_element.remove(quarter_externals)

                quarter_externals = etree.Element(
                    "Externals")  # Створюємо новий

                regional_contacts_element = quarter_element.find(
                    "RegionalContacts")
                if regional_contacts_element is not None:

                    regional_contacts_element.addnext(quarter_externals)
                else:

                    quarter_element.append(quarter_externals)

                parcel_externals = parcel_metric_info.find("Externals")
                if parcel_externals is not None:

                    old_boundary = quarter_externals.find("Boundary")
                    if old_boundary is not None:
                        quarter_externals.remove(old_boundary)
                    quarter_externals.append(etree.fromstring(
                        etree.tostring(parcel_externals.find("Boundary"))))

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                polygon.addInteriorRing(self._coord_to_polygon(
                    internal_coords).exteriorRing())

            feature = QgsFeature(self.layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            object_shape = ""
            if processor:
                try:
                    exterior_shape = processor._get_polyline_object_shape(externals_lines) if externals_lines is not None else ""
                    interior_shape = processor._get_polyline_object_shape(internals_lines) if internals_lines is not None else ""
                    object_shape = "|".join([s for s in (exterior_shape, interior_shape) if s])
                except Exception:
                    object_shape = ""
            feature.setAttributes([object_id, object_shape])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        if hasattr(self, 'xml_ua_layers'):
            self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
