import os

try:
    from lxml import etree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsLineString,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.utils import iface

from .common import ensure_object_layer_fields, log_msg, logFile
from .data_models import ShapeInfo  # noqa


class AdjacentUnits:
    """Клас для обробки даних про суміжників з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, xml_ua_layers_instance, xml_data=None):
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.xml_data = xml_data
        self.xml_ua_layers = xml_ua_layers_instance

    def _set_fp_tp(self, line_elem, fp_val, tp_val):
        """Гарантовано створює або оновлює теги FP та TP в дереві XML."""
        if line_elem is None:
            return

        fp_elem = line_elem.find("FP")
        if fp_elem is None:
            fp_elem = ET.SubElement(line_elem, "FP")
        fp_elem.text = str(fp_val) if fp_val is not None else ""

        tp_elem = line_elem.find("TP")
        if tp_elem is None:
            tp_elem = ET.SubElement(line_elem, "TP")
        tp_elem.text = str(tp_val) if tp_val is not None else ""

    def _get_polylines_map(self):
        """Повертає словник {ULID: [список_точок]} з MetricInfo."""
        polylines = {}
        for pl in self.root.findall(".//MetricInfo/Polyline/PL"):
            ulid = pl.findtext("ULID")
            pts = [p.text for p in pl.findall("Points/P") if p.text]
            if ulid:
                polylines[ulid] = pts
        return polylines

    def _get_parcel_ordered_points(self):
        """Отримує послідовну межу точок (UIDP) Ділянки для перевірки напрямку обходу."""
        polylines = self._get_polylines_map()

        boundary_lines_ulids = [
            ln.findtext("ULID")
            for ln in self.root.findall(".//ParcelMetricInfo/Externals/Boundary/Lines/Line")
            if ln.findtext("ULID")
        ]

        ordered_uidp = []
        if boundary_lines_ulids:
            first = boundary_lines_ulids[0]
            ordered_uidp.extend(polylines.get(first, []))
            for ulid in boundary_lines_ulids[1:]:
                pts = polylines.get(ulid, [])
                if not pts:
                    continue
                if ordered_uidp and pts[0] == ordered_uidp[-1]:
                    ordered_uidp.extend(pts[1:])
                elif ordered_uidp and pts[-1] == ordered_uidp[-1]:
                    ordered_uidp.extend(list(reversed(pts[:-1])))
                else:
                    ordered_uidp.extend(pts)
        return ordered_uidp

    def _should_invert_adjacent(self, adj_pts, parcel_pts):
        """Перевіряє, чи напрямок обходу Суміжника протилежний Ділянці."""
        if not parcel_pts or len(adj_pts) < 2:
            return False

        circular_parcel = parcel_pts + parcel_pts

        def is_sublist(sub, main):
            n = len(sub)
            for i in range(len(main) - n + 1):
                if main[i:i + n] == sub:
                    return True
            return False

        if is_sublist(adj_pts, circular_parcel):
            return False
        if is_sublist(list(reversed(adj_pts)), circular_parcel):
            return True

        indices = [parcel_pts.index(p) for p in adj_pts if p in parcel_pts]
        if len(indices) >= 2:
            diffs = [(indices[i + 1] - indices[i]) % len(parcel_pts) for i in range(len(indices) - 1)]
            avg_diff = sum(diffs) / len(diffs)
            if avg_diff > len(parcel_pts) / 2:
                return True

        return False

    def add_adjacents_layer(self):
        """Створює та заповнює шар 'Суміжники' згідно з алгоритмом обходу."""
        parcel_info = self.root.find(".//ParcelInfo")
        adjacents_parent = parcel_info.find("AdjacentUnits") if parcel_info is not None else None
        if adjacents_parent is None:
            return None

        layer_name = "Суміжники"

        layers_to_remove = [
            child.layerId() for child in self.group.children() if child.name() == layer_name
        ]
        if layers_to_remove:
            QgsProject.instance().removeMapLayers(layers_to_remove)

        self.layer = QgsVectorLayer(
            f"LineString?crs={self.crs_epsg}", layer_name, "memory"
        )
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

        parcel_pts = self._get_parcel_ordered_points()
        polylines = self._get_polylines_map()

        for adjacent in adjacents_parent.findall(".//AdjacentUnitInfo"):
            object_id_text = str(adjacent.get("object_id") or "").strip()
            boundary_lines = adjacent.find(".//AdjacentBoundary/Lines")
            if boundary_lines is not None:
                try:
                    from .topology import GeometryProcessor
                    processor = GeometryProcessor(self.root.getroottree())

                    # 1. Обчислюємо object_shape Суміжника
                    object_shape = processor._get_polyline_object_shape(boundary_lines)
                    adj_pts = object_shape.split('-') if object_shape else []

                    # 2. Перевіряємо напрям обходу відносно Ділянки
                    should_invert = self._should_invert_adjacent(adj_pts, parcel_pts)

                    boundary_coords = self.xml_ua_layers.lines_element2polyline(boundary_lines)
                    lines_list = list(boundary_lines.findall("Line"))

                    # 3. Якщо напрям протилежний — інвертуємо Суміжник і його object_shape
                    if should_invert:
                        adj_pts = list(reversed(adj_pts))
                        object_shape = "-".join(adj_pts)
                        if boundary_coords:
                            boundary_coords = list(reversed(boundary_coords))

                        if lines_list:
                            for line_elem in lines_list:
                                boundary_lines.remove(line_elem)
                            for line_elem in reversed(lines_list):
                                boundary_lines.append(line_elem)
                            lines_list = list(reversed(lines_list))

                    # 4. FP/TP обчислюємо з object_shape / точок поліліній та записуємо в XML
                    if len(lines_list) == 1 and adj_pts:
                        self._set_fp_tp(lines_list[0], adj_pts[0], adj_pts[-1])
                    elif len(lines_list) > 1:
                        for line_elem in lines_list:
                            ulid = line_elem.findtext("ULID")
                            pts = polylines.get(ulid, [])
                            if pts:
                                f_pt = pts[-1] if should_invert else pts[0]
                                t_pt = pts[0] if should_invert else pts[-1]
                                self._set_fp_tp(line_elem, f_pt, t_pt)

                    # 5. Перевірка на дублікати та додавання до дерева XML і карти QGIS
                    normalized_shape = "-".join(sorted(object_shape.split('-')))
                    if normalized_shape in existing_shapes_in_layer:
                        iface.messageBar().pushMessage(
                            "Попередження",
                            f"Знайдено дублікат геометрії суміжника (shape: {object_shape}). Об'єкт не буде додано на карту.",
                            level=Qgis.Warning,
                            duration=10
                        )
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

                except Exception as e:
                    log_msg(logFile, f"ПОМИЛКА обробки суміжника: {str(e)}")
                    continue

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer

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