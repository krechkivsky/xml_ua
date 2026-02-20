

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
    QgsProject
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from .data_models import ShapeInfo  # noqa
from .common import ensure_object_layer_fields, log_msg, insert_element_in_order, log_calls
from .common import logFile


class Restrictions:
    """Клас для обробки даних про обмеження з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з обмеженнями.

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

        line_string = QgsLineString(
            [QgsPointXY(p.y(), p.x()) for p in coordinates])
        polygon = QgsPolygon(line_string)
        return polygon

    def redraw_restrictions_layer(self, layer):
        """Очищує та заповнює існуючий шар 'Обмеження'."""
        provider = layer.dataProvider()
        layer.startEditing()
        layer.deleteFeatures(layer.allFeatureIds())
        ensure_object_layer_fields(layer)

        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.root.getroottree())
        except Exception:
            processor = None

        restrictions_parent = self.root.find(".//ParcelInfo/Restrictions")
        if restrictions_parent is None:
            layer.commitChanges()
            return

        for restriction in restrictions_parent.findall(".//RestrictionInfo"):
            restriction_code = restriction.findtext(".//RestrictionCode")
            restriction_name = restriction.findtext(".//RestrictionName")
            start_date = restriction.findtext(
                ".//RestrictionTerm/Time/StartDate")
            expiration_date = restriction.findtext(
                ".//RestrictionTerm/Time/ExpirationDate")

            object_id_text = str(restriction.get("object_id") or "").strip()

            object_id_text = str(restriction.get("object_id") or "").strip()
            externals_element = restriction.find(".//Externals")
            object_shape = ""
            if processor and externals_element is not None:
                try:
                    object_shape = processor.get_object_shape_from_externals(externals_element)
                except Exception:
                    object_shape = ""

            externals_lines = restriction.find(".//Externals/Boundary/Lines")
            external_coords = self.lines_to_coords(
                externals_lines) if externals_lines is not None else []

            internal_coords_list = [self.lines_to_coords(b.find('Lines')) for b in restriction.findall(
                ".//Internals/Boundary") if b.find('Lines') is not None]

            polygon = self._coord_to_polygon(external_coords)
            if not polygon.isEmpty():
                for internal_coords in internal_coords_list:
                    if internal_coords:

                        interior_ring = QgsLineString(
                            [QgsPointXY(p.y(), p.x()) for p in internal_coords])
                        polygon.addInteriorRing(interior_ring)

            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            object_id = int(object_id_text) if object_id_text.isdigit() else None
            feature.setAttributes([object_id, object_shape])
            provider.addFeature(feature)
        layer.commitChanges()

    def add_restrictions_layer(self):
        """Створює та заповнює шар 'Обмеження'."""
        parcel_info = self.root.find(".//ParcelInfo")
        restrictions_parent = parcel_info.find("Restrictions")
        if restrictions_parent is None:

            return None

        layer_name = "Обмеження"
        self.layer = QgsVectorLayer(
            f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")
        self.layer.setCustomProperty("skip_save_dialog", True)
        self.layer.loadNamedStyle(os.path.join(
            self.plugin_dir, "templates", "restriction.qml"))
        provider = self.layer.dataProvider()

        ensure_object_layer_fields(self.layer)

        existing_shapes_in_layer = set()
        if self.xml_data:
            for si in self.xml_data.shapes:
                if si.layer_id == self.layer.id():
                    existing_shapes_in_layer.add(si.object_shape)

        used_object_ids = set()
        for restriction_info in restrictions_parent.findall(".//RestrictionInfo"):
            obj_id_text = str(restriction_info.get("object_id") or "").strip()
            if obj_id_text.isdigit():
                used_object_ids.add(int(obj_id_text))
        next_object_id = 1

        for restriction in restrictions_parent.findall(".//RestrictionInfo"):
            restriction_code = restriction.findtext(".//RestrictionCode")
            restriction_name = restriction.findtext(".//RestrictionName")
            start_date = restriction.findtext(
                ".//RestrictionTerm/Time/StartDate")
            expiration_date = restriction.findtext(
                ".//RestrictionTerm/Time/ExpirationDate")

            object_id_text = str(restriction.get("object_id") or "").strip()
            if not object_id_text.isdigit():
                while next_object_id in used_object_ids:
                    next_object_id += 1
                object_id_text = str(next_object_id)
                used_object_ids.add(next_object_id)
                next_object_id += 1
                restriction.set("object_id", object_id_text)

            try:
                from .topology import GeometryProcessor
                processor = GeometryProcessor(self.root.getroottree())
            except Exception as e:
                log_msg(
                    logFile, f"Не вдалося створити GeometryProcessor в Restrictions: {e}")
                processor = None

            externals_element = restriction.find(".//Externals")
            if externals_element is None:

                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(
                    externals_lines) if externals_lines is not None else []

            internal_coords_list = [self.lines_to_coords(b.find('Lines')) for b in restriction.findall(
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
                object_shape = "|".join([exterior_shape] + interior_shapes)

                if object_shape in existing_shapes_in_layer:
                    iface.messageBar().pushMessage("Попередження",
                                                   f"Знайдено дублікат геометрії обмеження (shape: {object_shape}). Об'єкт не буде додано на карту.", level=Qgis.Warning, duration=10)
                    log_msg(
                        logFile, f"ПОПЕРЕДЖЕННЯ: Пропущено дублікат обмеження з object_shape: {object_shape}")
                    continue
                existing_shapes_in_layer.add(object_shape)

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

            if self.xml_data and object_id_text:
                shape_info = ShapeInfo(
                    layer_id=self.layer.id(),
                    object_id=object_id_text,
                    object_shape=object_shape)
                self.xml_data.shapes.append(shape_info)
                log_msg(
                    logFile, f"Додавання об'єкта до shapes: Обмеження, ID:{object_id_text}, shape='{object_shape}'")
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
