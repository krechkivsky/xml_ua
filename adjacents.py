

import os
from qgis.core import (
    QgsWkbTypes,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsLineString,
    QgsPointXY,
    QgsProject
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from .data_models import ShapeInfo  # noqa
from .common import ensure_object_layer_fields, log_msg, insert_element_in_order, log_calls, logFile


class AdjacentUnits:
    """Клас для обробки даних про суміжників з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, xml_ua_layers_instance, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з суміжниками.

        Args:
            root: Кореневий елемент XML-дерева.
            crs_epsg (str): EPSG-код системи координат.
            group (QgsLayerTreeGroup): Група шарів у QGIS.
            plugin_dir (str): Шлях до директорії плагіна.
            xml_ua_layers_instance: Екземпляр класу xmlUaLayers для доступу до його методів.
        """
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.xml_data = xml_data
        self.xml_ua_layers = xml_ua_layers_instance

    def _get_proprietor_name(self, adjacent_element):
        """Отримує ім'я власника з елемента AdjacentUnitInfo."""
        proprietor = ""
        natural_person = adjacent_element.find(
            ".//Proprietor/NaturalPerson/FullName")
        legal_entity = adjacent_element.find(".//Proprietor/LegalEntity")

        if natural_person is not None:
            last_name = natural_person.findtext("LastName", "")
            first_name = natural_person.findtext("FirstName", "")
            middle_name = natural_person.findtext("MiddleName", "")
            proprietor = f"{last_name} {first_name} {middle_name}".strip()
        elif legal_entity is not None:
            proprietor = legal_entity.findtext("Name", "")

        return proprietor

    def add_adjacents_layer(self):
        """Створює та заповнює шар 'Суміжники'."""
        parcel_info = self.root.find(".//ParcelInfo")
        adjacents_parent = parcel_info.find("AdjacentUnits")
        if adjacents_parent is None:

            return None

        layer_name = "Суміжники"

        layers_to_remove = [
            child.layerId() for child in self.group.children() if child.name() == layer_name]
        if layers_to_remove:
            QgsProject.instance().removeMapLayers(layers_to_remove)

        self.layer = QgsVectorLayer(
            f"LineString?crs={self.crs_epsg}", layer_name, "memory")
        self.layer.loadNamedStyle(os.path.join(
            self.plugin_dir, "templates", "adjacent.qml"))

        self.layer.setCustomProperty("skip_save_dialog", True)

        provider = self.layer.dataProvider()

        ensure_object_layer_fields(self.layer)

        existing_shapes_in_layer = set()
        if self.xml_data:
            for si in self.xml_data.shapes:
                if si.layer_id == self.layer.id():

                    shape_parts = si.object_shape.split('-')
                    normalized_shape = "-".join(sorted(shape_parts))
                    existing_shapes_in_layer.add(normalized_shape)

        used_object_ids = set()
        for adj_info in adjacents_parent.findall(".//AdjacentUnitInfo"):
            obj_id_text = str(adj_info.get("object_id") or "").strip()
            if obj_id_text.isdigit():
                used_object_ids.add(int(obj_id_text))
        next_object_id = 1

        for adjacent in adjacents_parent.findall(".//AdjacentUnitInfo"):
            object_id_text = str(adjacent.get("object_id") or "").strip()
            boundary_lines = adjacent.find(".//AdjacentBoundary/Lines")
            if boundary_lines is not None:
                try:

                    from .topology import GeometryProcessor
                    processor = GeometryProcessor(self.root.getroottree())
                    object_shape = processor._get_polyline_object_shape(
                        boundary_lines)

                    normalized_shape = "-".join(
                        sorted(object_shape.split('-')))
                    if normalized_shape in existing_shapes_in_layer:
                        iface.messageBar().pushMessage("Попередження",
                                                       f"Знайдено дублікат геометрії суміжника (shape: {object_shape}). Об'єкт не буде додано на карту.", level=Qgis.Warning, duration=10)
                        log_msg(
                            logFile, f"ПОПЕРЕДЖЕННЯ: Пропущено дублікат суміжника з object_shape: {object_shape}")
                        continue
                    existing_shapes_in_layer.add(normalized_shape)

                    if not object_id_text.isdigit():
                        while next_object_id in used_object_ids:
                            next_object_id += 1
                        object_id_text = str(next_object_id)
                        used_object_ids.add(next_object_id)
                        next_object_id += 1
                        adjacent.set("object_id", object_id_text)

                    boundary_coords = self.xml_ua_layers.lines_element2polyline(
                        boundary_lines)
                    if boundary_coords and len(boundary_coords) >= 2:
                        line_string = QgsLineString(
                            [QgsPointXY(p.y(), p.x()) for p in boundary_coords])
                        feature = QgsFeature(self.layer.fields())
                        feature.setGeometry(QgsGeometry(line_string))
                        object_id = int(object_id_text) if object_id_text.isdigit() else None
                        feature.setAttributes([object_id, object_shape])

                        if self.xml_data and object_id_text:
                            shape_info = ShapeInfo(
                                layer_id=self.layer.id(),
                                object_id=object_id_text,
                                object_shape=object_shape)
                            self.xml_data.shapes.append(shape_info)

                        provider.addFeature(feature)

                except ValueError as e:

                    continue

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
