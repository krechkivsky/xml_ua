

import os
from qgis.core import (
    Qgis,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPolygon,
    QgsLineString,
    QgsPointXY,
    QgsWkbTypes,
    QgsProject,
    QgsLayerTreeLayer
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from .data_models import ShapeInfo  # noqa
from .common import ensure_object_layer_fields, log_msg, insert_element_in_order, log_calls
from .common import logFile


class LandsParcels:
    """Клас для обробки угідь з XML-файлу."""

    def __init__(self, tree_or_root, crs_epsg, group, plugin_dir, layers_root, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з угіддями.

        Args:
            root: Кореневий елемент XML-дерева.
            crs_epsg (str): EPSG-код системи координат.
            group (QgsLayerTreeGroup): Група шарів у QGIS.
            plugin_dir (str): Шлях до директорії плагіна.
            layers_root (QgsLayerTreeGroup): Кореневий вузол дерева шарів QGIS.
            lines_to_coords_func (function): Функція для перетворення ліній у координати.
            xml_ua_layers_instance: Екземпляр класу xmlUaLayers для доступу до його методів.
        """

        if hasattr(tree_or_root, 'getroot'):
            self.tree = tree_or_root
            self.root = tree_or_root.getroot()
        else:
            self.root = tree_or_root
            self.tree = tree_or_root.getroottree()

        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.lines_to_coords = lines_to_coords_func
        self.xml_ua_layers = xml_ua_layers_instance
        self.xml_data = xml_data

    def _coord_to_polygon(self, coordinates):
        """Формує полігон із заданого списку координат."""
        if not coordinates:
            return QgsPolygon()

        line_string = QgsLineString(
            [QgsPointXY(p.y(), p.x()) for p in coordinates])
        polygon = QgsPolygon(line_string)
        return polygon

    def redraw_lands_layer(self, layer):
        """Очищує та заповнює існуючий шар 'Угіддя'."""
        provider = layer.dataProvider()
        layer.startEditing()
        layer.deleteFeatures(layer.allFeatureIds())

        ensure_object_layer_fields(layer)

        lands_parcel_container = self.root.find(".//ParcelInfo/LandsParcel")
        if lands_parcel_container is None:
            layer.commitChanges()
            return

        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.tree)
            log_msg(
                logFile, "GeometryProcessor успішно створено в redraw_lands_layer.")
        except Exception as e:
            log_msg(
                logFile, f"Не вдалося створити GeometryProcessor в LandsParcels (redraw): {e}")
            processor = None

        for land_parcel_info in lands_parcel_container.findall("LandParcelInfo"):
            object_id_text = str(land_parcel_info.get("object_id") or "").strip()
            metric_info = land_parcel_info.find("MetricInfo")
            if metric_info is None:
                continue

            size_element = metric_info.find("./Area/Size")
            size = float(
                size_element.text) if size_element is not None and size_element.text else None

            externals_element = metric_info.find("Externals")

            object_shape = processor.get_object_shape_from_externals(
                externals_element) if processor else ""

            external_coords = self.lines_to_coords(externals_element.find(
                "Boundary/Lines"), context='modify') if externals_element is not None and externals_element.find("Boundary/Lines") is not None else []

            internal_coords_list = []
            internals_container = externals_element.find(
                "Internals") if externals_element is not None else None
            if internals_container is not None:
                internal_coords_list = [self.lines_to_coords(b.find(
                    'Lines'), context='modify') for b in internals_container.findall("Boundary") if b.find('Lines') is not None]

            polygon = self._create_polygon_with_holes(
                external_coords, internal_coords_list)
            if not polygon.isEmpty():
                feature = QgsFeature(layer.fields())
                feature.setGeometry(QgsGeometry(polygon))
                object_id = int(object_id_text) if object_id_text.isdigit() else None
                feature.setAttributes([object_id, object_shape])
                provider.addFeature(feature)

        layer.commitChanges()
        log_msg(
            logFile, f"Шар '{layer.name()}' успішно перемальовано. Додано {layer.featureCount()} об'єкт(ів).")

    def _create_polygon_with_holes(self, exterior_coords, interior_coords_list):
        """Створює полігон з отворами."""
        polygon = self._coord_to_polygon(exterior_coords)
        if not polygon.isEmpty():
            for interior_coords in interior_coords_list:
                if interior_coords:
                    interior_ring = QgsLineString(
                        [QgsPointXY(p.y(), p.x()) for p in interior_coords])
                    polygon.addInteriorRing(interior_ring)
        return polygon

    def add_lands_layer(self):
        """Створює та заповнює шар 'Угіддя'."""
        layer_name = "Угіддя"
        self.layer = QgsVectorLayer(
            f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")
        self.layer.setCustomProperty("skip_save_dialog", True)
        self.layer.loadNamedStyle(os.path.join(
            self.plugin_dir, "templates", "lands_parcel.qml"))
        provider = self.layer.dataProvider()

        ensure_object_layer_fields(self.layer)

        existing_shapes_in_layer = set()
        if self.xml_data:
            for si in self.xml_data.shapes:
                if si.layer_id == self.layer.id():
                    existing_shapes_in_layer.add(si.object_shape)

        parcel_info = self.root.find(".//ParcelInfo")
        lands_parcel_parent = parcel_info.find("LandsParcel")
        if lands_parcel_parent is None:
            lands_parcel_parent = etree.Element("LandsParcel")
            insert_element_in_order(parcel_info, lands_parcel_parent)

        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.root.getroottree())
        except Exception as e:
            log_msg(
                logFile, f"Не вдалося створити GeometryProcessor в LandsParcels: {e}")
            processor = None

        used_object_ids = set()
        for land_info in lands_parcel_parent.findall("LandParcelInfo"):
            obj_id_text = str(land_info.get("object_id") or "").strip()
            if obj_id_text.isdigit():
                used_object_ids.add(int(obj_id_text))
        next_object_id = 1

        for lands_parcel in self.root.findall(".//LandsParcel/LandParcelInfo/MetricInfo"):
            land_parcel_info = lands_parcel.getparent()
            object_id_text = str(land_parcel_info.get("object_id") or "").strip() if land_parcel_info is not None else ""
            size_element = lands_parcel.find("./Area/Size")
            size = float(
                size_element.text) if size_element is not None and size_element.text else None

            externals_element = lands_parcel.find(".//Externals")
            if externals_element is None:

                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(
                    externals_lines) if externals_lines is not None else []

            internal_coords_list = [self.lines_to_coords(b.find('Lines')) for b in lands_parcel.findall(
                ".//Internals/Boundary") if b.find('Lines') is not None]

            object_shape = ""
            if processor and externals_element is not None:
                exterior_shape = processor._get_polyline_object_shape(
                    externals_element.find("Boundary/Lines"))
                interior_shapes = []
                internals_container = externals_element.find("Internals")
                if internals_container is not None:
                    interior_shapes = [processor._get_polyline_object_shape(internal.find(
                        "Boundary/Lines")) for internal in internals_container.findall("Boundary")]
                all_rings = [exterior_shape] + interior_shapes
                object_shape = "|".join(filter(None, all_rings))

                if object_shape in existing_shapes_in_layer:
                    iface.messageBar().pushMessage("Попередження",
                                                   f"Знайдено дублікат геометрії угіддя (shape: {object_shape}). Об'єкт не буде додано на карту.", level=Qgis.Warning, duration=10)
                    log_msg(
                        logFile, f"ПОПЕРЕДЖЕННЯ: Пропущено дублікат угіддя з object_shape: {object_shape}")
                    continue
                existing_shapes_in_layer.add(object_shape)

            if land_parcel_info is not None and not object_id_text.isdigit():
                while next_object_id in used_object_ids:
                    next_object_id += 1
                object_id_text = str(next_object_id)
                used_object_ids.add(next_object_id)
                next_object_id += 1
                land_parcel_info.set("object_id", object_id_text)

            polygon = self._coord_to_polygon(external_coords)
            if not polygon.isEmpty():
                for internal_coords in internal_coords_list:
                    if internal_coords:

                        interior_ring = QgsLineString(
                            [QgsPointXY(p.y(), p.x()) for p in internal_coords])
                        polygon.addInteriorRing(interior_ring)

            feature = QgsFeature(self.layer.fields())

            feature.setGeometry(QgsGeometry(polygon))
            object_id = int(object_id_text) if object_id_text.isdigit() else None
            feature.setAttributes([object_id, object_shape])

            if self.xml_data:
                shape_info = ShapeInfo(
                    layer_id=self.layer.id(),
                    object_id=object_id_text,
                    object_shape=object_shape)
                self.xml_data.shapes.append(shape_info)

            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
