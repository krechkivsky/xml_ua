

import os
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPolygon,
    QgsLineString,
    QgsPointXY,
    QgsWkbTypes,
    QgsProject
)
from .data_models import ShapeInfo  # noqa
from .common import ensure_object_layer_fields, logFile, log_msg


class CadastralParcel:
    """Клас для обробки земельної ділянки з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.lines_to_coords = lines_to_coords_func
        self.xml_ua_layers = xml_ua_layers_instance
        self.xml_data = xml_data

    def _coord_to_polygon(self, coordinates):
        if not coordinates:
            return QgsPolygon()
        exterior_ring = QgsLineString(
            [QgsPointXY(p.y(), p.x()) for p in coordinates])
        return QgsPolygon(exterior_ring)

    def add_parcel_layer(self):
        """Створює та заповнює шар 'Ділянка'."""
        layer_name = "Ділянка"
        self.layer = QgsVectorLayer(
            f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")

        self.layer.setCustomProperty("skip_save_dialog", True)

        self.layer.loadNamedStyle(os.path.join(
            self.plugin_dir, "templates", "parcel.qml"))
        provider = self.layer.dataProvider()

        ensure_object_layer_fields(self.layer)

        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.root.getroottree())
        except Exception as e:
            log_msg(
                logFile, f"Не вдалося створити GeometryProcessor в CadastralParcel: {e}")
            processor = None

        parcel_metric_info = self.root.find(".//ParcelMetricInfo")
        if parcel_metric_info is not None:
            parcel_id = parcel_metric_info.findtext("ParcelID")
            area_element = parcel_metric_info.find("./Area/Size")
            area = float(
                area_element.text) if area_element is not None and area_element.text else None

            externals_element = parcel_metric_info.find(".//Externals")
            if externals_element is None:
                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(
                    externals_lines) if externals_lines is not None else []

            internals_lines_list = parcel_metric_info.findall(".//Internals/Boundary/Lines")
            internal_coords_list = [
                self.lines_to_coords(lines_el) for lines_el in internals_lines_list if lines_el is not None
            ]

            object_shape = ""
            if processor and externals_element is not None:
                exterior_shape = processor._get_polyline_object_shape(
                    externals_lines)
                interior_shapes = []
                internals_container = parcel_metric_info.find(".//Internals")
                if internals_container is not None:
                    interior_shapes = [
                        processor._get_polyline_object_shape(internal.find("Boundary/Lines"))
                        for internal in internals_container.findall("Boundary")
                        if internal.find("Boundary/Lines") is not None
                    ]

                all_rings = [exterior_shape] + interior_shapes
                object_shape = "|".join(filter(None, all_rings))

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords_list and not polygon.isEmpty():
                for internal_coords in internal_coords_list:
                    if not internal_coords:
                        continue
                    interior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in internal_coords])
                    polygon.addInteriorRing(interior_ring)

            feature = QgsFeature(self.layer.fields())
            feature.setGeometry(QgsGeometry(polygon))

            object_id = 1
            feature.setAttributes([object_id, object_shape])

            if self.xml_data:
                shape_info = ShapeInfo(
                    layer_id=self.layer.id(),
                    object_id="parcel",  # Спеціальний ID для ділянки
                    object_shape=object_shape)
                shape_info.object_id = str(object_id)
                self.xml_data.shapes.append(shape_info)

            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        if hasattr(self, 'xml_ua_layers'):
            self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
