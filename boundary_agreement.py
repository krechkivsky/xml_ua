"""
boundary_agreement.py

Створення "Акту погодження меж" як окремого макету QGIS Layout.

Вимоги:
- Код створення "Кадастрового плану" не змінюємо.
- Для акту створюємо окрему групу "Акт погодження меж" за тими ж правилами, що і
  групу "Кадастровий план", але зі стилями *_act.qml (поки що копії *_plan.qml).
- Після створення макету відкриваємо його автоматично.
"""

from __future__ import annotations

import os
import shutil

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
    Qgis,
)

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from .common import PARCEL_MARGIN_FACTOR, log_calls, logFile
from qgis.PyQt.QtWidgets import QInputDialog

from .plan_layout import MAP_SIDE_MM, compute_map_scale
from .topology import GeometryProcessor
from .boundary_agreement_layout import BoundaryAgreementLayoutCreator


class BoundaryAgreementCreator:
    _ROLE_PROP_KEY = "xml_ua:role"
    _ROLE_PROP_VALUE = "boundary_agreement"

    def __init__(self, plugin):
        self.plugin = plugin
        self.iface = getattr(plugin, "iface", None)
        self.project = QgsProject.instance()

    def run(self):
        """
        Головний сценарій:
        - перевірити активну групу XML
        - підготувати групу "Акт погодження меж"
        - розрахувати масштаб (як для плану) + показати діалог
        - сформувати макет та відкрити його
        """
        if not self.plugin or not getattr(self.plugin, "dockwidget", None):
            QMessageBox.warning(self.iface.mainWindow(), "Помилка", "Док-віджет не ініціалізовано.")
            return None

        if getattr(self.plugin, "dockwidget", None):
            try:
                self.plugin.dockwidget.renumber_cadastral_codes()
            except Exception:
                pass

        group_name = None
        try:
            group_name = getattr(self.plugin.dockwidget.current_xml, "group_name", None)
        except Exception:
            group_name = None

        if not group_name:
            QMessageBox.warning(self.iface.mainWindow(), "Помилка", "Немає активного XML/групи для формування акту.")
            return None

        prep = self._prepare_group(group_name)
        if not prep:
            return None
        parent_group, act_group, extent = prep

        if extent is None:
            QMessageBox.warning(self.iface.mainWindow(), "Помилка", "Не вдалося визначити екстент для розрахунку масштабу.")
            return None

        scale_calc = compute_map_scale(extent=extent, map_side_mm=MAP_SIDE_MM, margin_factor=PARCEL_MARGIN_FACTOR)
        scale_value, _is_calculated_choice = self._choose_scale_with_dialog(scale_calc)
        if scale_value is None:
            return None

        creator = BoundaryAgreementLayoutCreator(self.iface, parent_group, self.project, plugin=self.plugin)
        layout = creator.create_layout(scale_value=int(scale_value))
        if layout is not None:
            try:
                self.iface.openLayoutDesigner(layout)
            except Exception:
                pass
        return layout

    def _choose_scale_with_dialog(self, scale_calc: int):
        """
        Копія логіки вибору масштабу (як у xml_ua.py), щоб модуль акту був автономним.

        return: (int | None, bool) -> (scale_value, is_calculated_choice)
        """
        nice_scales = [500, 1000, 2000, 5000]
        valid_nice = [s for s in nice_scales if s >= int(scale_calc)]

        options = []
        values = []

        options.append(f"Розрахунковий (1:{int(scale_calc)}) — максимальний")
        values.append(int(scale_calc))

        for s in valid_nice:
            options.append(f"Округлений 1:{int(s)} — ділянка менша")
            values.append(int(s))

        choice, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Вибір масштабу",
            "Оберіть масштаб плану:",
            options,
            0,
            False,
        )

        if not ok:
            return None, False

        idx = options.index(choice)
        return values[idx], (idx == 0)

    def _templates_dir(self) -> str:
        return os.path.join(os.path.dirname(__file__), "templates")

    def _ensure_act_style(self, act_filename: str) -> str:
        """
        Гарантує наявність templates/*_act.qml.
        Якщо його нема — копіює з відповідного *_plan.qml.
        """
        act_filename = str(act_filename or "").strip()
        templates_dir = self._templates_dir()
        act_path = os.path.join(templates_dir, act_filename)
        if os.path.exists(act_path):
            return act_path

        if act_filename.endswith("_act.qml"):
            plan_filename = act_filename.replace("_act.qml", "_plan.qml")
            plan_path = os.path.join(templates_dir, plan_filename)
            if os.path.exists(plan_path):
                try:
                    shutil.copyfile(plan_path, act_path)
                except Exception:
                    return plan_path
                return act_path if os.path.exists(act_path) else plan_path

        return act_path

    def _find_first_layer_node_by_name(self, group: QgsLayerTreeGroup, layer_name: str):
        for ch in group.children():
            if isinstance(ch, QgsLayerTreeLayer) and ch.name() == layer_name:
                return ch
            if isinstance(ch, QgsLayerTreeGroup):
                found = self._find_first_layer_node_by_name(ch, layer_name)
                if found:
                    return found
        return None

    def _collect_layer_ids(self, group: QgsLayerTreeGroup):
        layer_ids = []
        for ch in group.children():
            if isinstance(ch, QgsLayerTreeLayer):
                lyr = ch.layer()
                if lyr:
                    layer_ids.append(lyr.id())
            elif isinstance(ch, QgsLayerTreeGroup):
                layer_ids.extend(self._collect_layer_ids(ch))
        return layer_ids

    def _collect_groups_named(self, group: QgsLayerTreeGroup, group_name_to_find: str):
        groups = []
        for ch in group.children():
            if isinstance(ch, QgsLayerTreeGroup):
                if ch.name() == group_name_to_find:
                    groups.append(ch)
                groups.extend(self._collect_groups_named(ch, group_name_to_find))
        return groups

    def _prepare_group(self, group_name: str):
        project = self.project
        root = project.layerTreeRoot()
        xml_group = root.findGroup(group_name)
        if not xml_group:
            QMessageBox.warning(self.iface.mainWindow(), "Помилка", f"Не вдалося знайти групу '{group_name}' у дереві шарів.")
            return None

        # Перевіримо, що активний/виділений шар — "Ділянка" у цій групі (як для плану)
        selected_layers = self.iface.layerTreeView().selectedLayers()
        parcel_layer = next((layer for layer in selected_layers if layer and layer.name() == "Ділянка"), None)
        if not parcel_layer:
            parcel_node = self._find_first_layer_node_by_name(xml_group, "Ділянка")
            parcel_layer = parcel_node.layer() if parcel_node else None
        if not parcel_layer:
            QMessageBox.warning(self.iface.mainWindow(), "Помилка", "Спочатку виберіть шар 'Ділянка' у дереві шарів.")
            return None

        # Якщо попередній запуск акту завершився некоректно, в проєкті можуть залишатися
        # "висячі" шари (є в mapLayers, але немає вузла в дереві шарів). Це ламає
        # існуючий код створення кадастрового плану (root.findLayer(...)=None).
        self._cleanup_dangling_layers()

        # Видалити старі групи акту (та їхні шари) — аналогічно до плану
        existing_groups = self._collect_groups_named(xml_group, "Акт погодження меж")
        if existing_groups:
            def _depth(node):
                d = 0
                p = node.parent()
                while p is not None:
                    d += 1
                    p = p.parent()
                return d

            for old_group in sorted(existing_groups, key=_depth, reverse=True):
                layer_ids = self._collect_layer_ids(old_group)
                for layer_id in layer_ids:
                    lyr = project.mapLayer(layer_id)
                    if lyr and lyr.isEditable():
                        lyr.rollBack()
                if layer_ids:
                    project.removeMapLayers(layer_ids)
                old_parent = old_group.parent()
                if old_parent:
                    old_parent.removeChildNode(old_group)

        self.iface.messageBar().pushMessage(
            "Акт погодження меж",
            f"Створюємо групу 'Акт погодження меж' для групи: {group_name}...",
            level=Qgis.Info,
            duration=5,
        )

        act_group = xml_group.insertGroup(0, "Акт погодження меж")

        def _register_layer(layer):
            try:
                layer.setCustomProperty(self._ROLE_PROP_KEY, self._ROLE_PROP_VALUE)
            except Exception:
                pass

        def _attach_layer(group: QgsLayerTreeGroup, layer, index: int | None = None) -> bool:
            """
            Додає layer у дереві шарів саме в group (щоб root.findLayer(layer.id()) != None).
            Повертає True якщо вузол створено, інакше видаляє шар з проєкту та повертає False.
            """
            try:
                node = QgsLayerTreeLayer(layer)
                if index is None:
                    group.addChildNode(node)
                else:
                    group.insertChildNode(int(index), node)
            except Exception:
                try:
                    project.removeMapLayer(layer.id())
                except Exception:
                    pass
                return False

            try:
                if root.findLayer(layer.id()) is None:
                    project.removeMapLayer(layer.id())
                    try:
                        group.removeChildNode(node)
                    except Exception:
                        pass
                    return False
            except Exception:
                return False
            return True

        # XML (для ULID та UIDP)
        xml_tree = None
        xml_root = None
        try:
            xml_data = self.plugin.dockwidget.get_xml_data_for_group(group_name)
            xml_tree = getattr(xml_data, "tree", None) if xml_data else None
            xml_root = xml_tree.getroot() if xml_tree is not None else None
        except Exception:
            xml_tree = None
            xml_root = None

        namespace = ""
        try:
            if xml_root is not None and "}" in xml_root.tag:
                namespace = xml_root.tag.split("}")[0].strip("{")
        except Exception:
            namespace = ""

        # Контрольні точки (опційно)
        try:
            original_control_points_layer = None
            for layer in project.mapLayers().values():
                try:
                    node = root.findLayer(layer.id()) if layer else None
                    parent = node.parent() if node else None
                    if layer and layer.name() == "Закріплені вузли" and parent and parent.name() == group_name:
                        original_control_points_layer = layer
                        break
                except Exception:
                    continue

            if original_control_points_layer:
                duplicated = original_control_points_layer.clone()
                duplicated.setName("Закріплені вузли")
                project.addMapLayer(duplicated, False)
                _register_layer(duplicated)

                style_path = self._ensure_act_style("control_point_act.qml")
                if os.path.exists(style_path):
                    duplicated.loadNamedStyle(style_path)
                    duplicated.triggerRepaint()

                _attach_layer(act_group, duplicated, index=0)
        except Exception as e:
            log_calls(logFile, f"BoundaryAgreement: control points clone failed: {e}")

        # Дублікати шарів як у плані (але зі стилями *_act.qml)
        layer_style_map = {
            "Ділянка": "parcel_act.qml",
            "Угіддя": "lands_parcel_act.qml",
            "Оренда": "lease_act.qml",
            "Суборенда": "sublease_act.qml",
            "Обмеження": "restrictions_act.qml",
        }

        for layer_name, style_file in layer_style_map.items():
            original_layer = None
            for layer in project.mapLayers().values():
                try:
                    node = root.findLayer(layer.id()) if layer else None
                    parent = node.parent() if node else None
                    if layer and layer.name() == layer_name and parent and parent.name() == group_name:
                        original_layer = layer
                        break
                except Exception:
                    continue

            if not original_layer:
                continue

            duplicated = original_layer.clone()
            duplicated.setName(layer_name)
            project.addMapLayer(duplicated, False)
            _register_layer(duplicated)

            style_path = self._ensure_act_style(style_file)
            if os.path.exists(style_path):
                duplicated.loadNamedStyle(style_path)
                duplicated.triggerRepaint()

            _attach_layer(act_group, duplicated)

        # Суміжники (дублікат оригінального шару)
        self._create_adjacent_parcels_layer(act_group, group_name, attach_layer=_attach_layer, register_layer=_register_layer)

        # Полілінії — memory, відфільтровані по ULID межі ділянки (як у плані)
        self._create_boundary_lines_layer(
            act_group, group_name, xml_root, namespace, attach_layer=_attach_layer, register_layer=_register_layer
        )

        # Вузли ділянки (memory)
        self._create_parcel_nodes_layer(act_group, group_name, attach_layer=_attach_layer, register_layer=_register_layer)

        # Вузли суміжників (літерація)
        if xml_tree is not None and xml_root is not None:
            self._add_adjacent_points(
                act_group, group_name, xml_tree, xml_root, attach_layer=_attach_layer, register_layer=_register_layer
            )

        # Ховаємо оригінальні шари групи (як для плану)
        for child in xml_group.children():
            if isinstance(child, QgsLayerTreeLayer):
                child.setItemVisibilityChecked(False)

        extent = self._act_group_extent(act_group)

        self.iface.messageBar().pushMessage(
            "Акт погодження меж",
            f"Групу 'Акт погодження меж' створено для групи: {group_name}",
            level=Qgis.Success,
            duration=5,
        )

        return xml_group, act_group, extent

    def _create_adjacent_parcels_layer(
        self,
        act_group: QgsLayerTreeGroup,
        group_name: str,
        attach_layer,
        register_layer,
    ):
        project = self.project
        root = project.layerTreeRoot()
        original_layer = None
        adj_layer_name = "Суміжники"

        for layer in project.mapLayers().values():
            node = root.findLayer(layer.id()) if layer else None
            parent = node.parent() if node else None
            if layer and layer.name() == adj_layer_name and parent and parent.name() == group_name:
                original_layer = layer
                break

        if not original_layer:
            log_calls(logFile, f"BoundaryAgreement: original '{adj_layer_name}' not found in group '{group_name}'")
            return

        duplicated = original_layer.clone()
        duplicated.setName(adj_layer_name)
        project.addMapLayer(duplicated, False)
        register_layer(duplicated)
        if not attach_layer(act_group, duplicated):
            return

        style_path = self._ensure_act_style("adjacent_act.qml")
        if os.path.exists(style_path):
            duplicated.loadNamedStyle(style_path)
            duplicated.triggerRepaint()

    def _create_boundary_lines_layer(
        self,
        act_group: QgsLayerTreeGroup,
        group_name: str,
        xml_root,
        namespace: str,
        attach_layer,
        register_layer,
    ):
        project = self.project
        root = project.layerTreeRoot()

        if xml_root is None or not namespace:
            return

        parcel_ulids = []
        try:
            parcel_info_path = f".//{{{namespace}}}CadastralZoneInfo/{{{namespace}}}CadastralQuarters/{{{namespace}}}CadastralQuarterInfo/{{{namespace}}}Parcels/{{{namespace}}}ParcelInfo"
            for parcel_info in xml_root.findall(parcel_info_path):
                parcel_metric_info_path = f"./{{{namespace}}}ParcelMetricInfo/{{{namespace}}}Externals/{{{namespace}}}Boundary/{{{namespace}}}Lines/{{{namespace}}}Line"
                for line in parcel_info.findall(parcel_metric_info_path):
                    ulid_elem = line.find(f"./{{{namespace}}}ULID")
                    if ulid_elem is not None and ulid_elem.text:
                        parcel_ulids.append(ulid_elem.text)
        except Exception:
            parcel_ulids = []

        original_layer = None
        for layer in project.mapLayers().values():
            node = root.findLayer(layer.id()) if layer else None
            parent = node.parent() if node else None
            if layer and layer.name() == "Полілінії" and parent and parent.name() == group_name:
                original_layer = layer
                break

        if not original_layer:
            return

        try:
            geom_type_str = QgsWkbTypes.displayString(original_layer.wkbType())
            crs = original_layer.crs().authid()
            mem = QgsVectorLayer(f"{geom_type_str}?crs={crs}", "Полілінії", "memory")
            prov = mem.dataProvider()
            prov.addAttributes(original_layer.fields())
            mem.updateFields()

            feats = [feat for feat in original_layer.getFeatures()]
            ulid_field_index = original_layer.fields().indexFromName("ULID")
            if ulid_field_index >= 0 and parcel_ulids:
                feats = [f for f in feats if f.attributes()[ulid_field_index] in parcel_ulids]

            prov.addFeatures(feats)
            mem.updateExtents()
            project.addMapLayer(mem, False)
            register_layer(mem)

            style_path = self._ensure_act_style("lines_act.qml")
            if os.path.exists(style_path):
                mem.loadNamedStyle(style_path)
                mem.triggerRepaint()

            if not attach_layer(act_group, mem):
                return
            try:
                mem.startEditing()
            except Exception:
                pass
        except Exception as e:
            log_calls(logFile, f"BoundaryAgreement: lines layer failed: {e}")

    def _create_parcel_nodes_layer(
        self,
        act_group: QgsLayerTreeGroup,
        group_name: str,
        attach_layer,
        register_layer,
    ):
        """
        Memory-шар 'Вузли ділянки' як у плані, але зі стилем points_parcel_act.qml.
        """
        project = self.project

        lines_layer = None
        for ch in act_group.children():
            if isinstance(ch, QgsLayerTreeLayer) and ch.layer().name() == "Полілінії":
                lines_layer = ch.layer()
                break
        if not lines_layer:
            return

        # Оригінальний шар "Вузли" беремо з групи XML
        xml_group = act_group.parent() if act_group else None
        nodes_layer = None
        if isinstance(xml_group, QgsLayerTreeGroup):
            for child in xml_group.children():
                if isinstance(child, QgsLayerTreeLayer):
                    lyr = child.layer()
                    if lyr and lyr.name() == "Вузли":
                        nodes_layer = lyr
                        break

        if not nodes_layer:
            return

        parcel_vertices = set()
        for feat in lines_layer.getFeatures():
            geom = feat.geometry()
            if not geom:
                continue
            for pt in geom.vertices():
                parcel_vertices.add((round(pt.x(), 6), round(pt.y(), 6)))

        if not parcel_vertices:
            return

        crs = nodes_layer.crs().authid()
        mem_layer = QgsVectorLayer(f"Point?crs={crs}", "Вузли ділянки", "memory")
        prov = mem_layer.dataProvider()
        prov.addAttributes(nodes_layer.fields())
        mem_layer.updateFields()

        feats_to_add = []
        for f in nodes_layer.getFeatures():
            pt = f.geometry().asPoint()
            key = (round(pt.x(), 6), round(pt.y(), 6))
            if key in parcel_vertices:
                feats_to_add.append(f)

        prov.addFeatures(feats_to_add)
        mem_layer.updateExtents()

        style_path = self._ensure_act_style("points_parcel_act.qml")
        if os.path.exists(style_path):
            mem_layer.loadNamedStyle(style_path)
            mem_layer.triggerRepaint()

        project.addMapLayer(mem_layer, False)
        register_layer(mem_layer)
        attach_layer(act_group, mem_layer)

    def _add_adjacent_points(
        self,
        act_group: QgsLayerTreeGroup,
        group_name: str,
        xml_tree,
        xml_root,
        attach_layer,
        register_layer,
    ):
        """
        Аналог add_adjacent_points() для акту, але стиль points_act.qml.
        """
        ns = ""
        if "}" in xml_root.tag:
            ns = xml_root.tag.split("}")[0].strip("{")
        ns_map = {"ns": ns} if ns else None
        ns_prefix = "ns:" if ns else ""

        parcel_boundary_uidps = []
        parcel_metric_info_xpath = f".//{ns_prefix}ParcelMetricInfo"
        parcel_metric_info = xml_root.find(parcel_metric_info_xpath, namespaces=ns_map)
        if parcel_metric_info:
            externals_path = f"{ns_prefix}Externals/{ns_prefix}Boundary/{ns_prefix}Lines"
            externals_lines = parcel_metric_info.find(externals_path, namespaces=ns_map)
            if externals_lines is not None:
                processor = GeometryProcessor(xml_tree)
                shape_str = processor._get_polyline_object_shape(externals_lines)
                if shape_str:
                    parcel_boundary_uidps = shape_str.split("-")
        if not parcel_boundary_uidps:
            return
        parcel_boundary_uidps_set = set(parcel_boundary_uidps)

        points_to_literate_set = set()
        adjacent_units_xpath = f".//{ns_prefix}AdjacentUnits/{ns_prefix}AdjacentUnitInfo"
        for adj_unit in xml_root.findall(adjacent_units_xpath, namespaces=ns_map):
            lines_container = adj_unit.find(f".//{ns_prefix}AdjacentBoundary/{ns_prefix}Lines", namespaces=ns_map)
            if lines_container is not None:
                for line in lines_container.findall(f"{ns_prefix}Line", namespaces=ns_map):
                    ulid = line.findtext(f"{ns_prefix}ULID", namespaces=ns_map)
                    line_data = next(
                        (item for item in self.plugin.dockwidget.layers_obj.lines_handler.xml_lines if item["ULID"] == ulid),
                        None,
                    )
                    if line_data and len(line_data["Points"]) == 2:
                        p1_uidp, p2_uidp = line_data["Points"]
                        p1_on_boundary = p1_uidp in parcel_boundary_uidps_set
                        p2_on_boundary = p2_uidp in parcel_boundary_uidps_set

                        if p1_on_boundary and not p2_on_boundary:
                            points_to_literate_set.add(p1_uidp)
                        elif not p1_on_boundary and p2_on_boundary:
                            points_to_literate_set.add(p2_uidp)

        if not points_to_literate_set:
            return

        final_points_to_literate = [uidp for uidp in parcel_boundary_uidps if uidp in points_to_literate_set]
        if not final_points_to_literate:
            return

        def generate_letters():
            alphabet = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
            n = len(alphabet)
            count = 0
            while True:
                if count < n:
                    yield alphabet[count]
                else:
                    yield alphabet[(count // n) - 1] + alphabet[count % n]
                count += 1

        letter_generator = generate_letters()

        layer_name = "Вузли суміжників"
        crs = QgsProject.instance().crs().authid()
        layer = QgsVectorLayer(f"Point?crs={crs}", layer_name, "memory")
        provider = layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("PN", QVariant.String, "Ім'я точки"))
        fields.append(QgsField("LITERA", QVariant.String, "Літера"))
        provider.addAttributes(fields)
        layer.updateFields()

        points_handler = self.plugin.dockwidget.layers_obj.points_handler
        qgis_points = points_handler.qgisPoints

        features_to_add = []
        for uidp in final_points_to_literate:
            if uidp in qgis_points:
                point_data = next((p for p in points_handler.xmlPoints if p["UIDP"] == uidp), None)
                if point_data:
                    feat = QgsFeature(fields)
                    qgs_point = qgis_points[uidp]
                    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(qgs_point.y(), qgs_point.x())))
                    litera = next(letter_generator)
                    feat.setAttributes([point_data.get("PN", ""), litera])
                    features_to_add.append(feat)

        if features_to_add:
            # У плані останній дубль видаляється — повторюємо поведінку.
            try:
                del features_to_add[-1]
            except Exception:
                pass
            provider.addFeatures(features_to_add)

        style_path = self._ensure_act_style("points_act.qml")
        if os.path.exists(style_path):
            layer.loadNamedStyle(style_path)
            labeling = layer.labeling()
            if labeling:
                settings = labeling.settings()
                settings.fieldName = "LITERA"
                labeling.setSettings(settings)
                layer.setLabeling(labeling)

        QgsProject.instance().addMapLayer(layer, False)
        register_layer(layer)
        attach_layer(act_group, layer)

    def _act_group_extent(self, act_group: QgsLayerTreeGroup):
        extent = None
        # 1) пріоритет "Суміжники"
        for child in act_group.children():
            if isinstance(child, QgsLayerTreeLayer):
                lyr = child.layer()
                if lyr and lyr.name() == "Суміжники":
                    extent = lyr.extent()
                    break

        if extent is None:
            for child in act_group.children():
                if isinstance(child, QgsLayerTreeLayer):
                    lyr = child.layer()
                    if lyr:
                        extent = lyr.extent() if extent is None else extent.combineExtentWith(lyr.extent())
        return extent

    def _cleanup_dangling_layers(self):
        """
        Видаляє шари акту, які є в QgsProject.mapLayers(), але не мають вузла у дереві.
        Це критично, бо існуючий код кадастрового плану викликає root.findLayer(...).parent()
        без перевірки на None.
        """
        project = self.project
        root = project.layerTreeRoot()
        to_remove = []
        for lyr in project.mapLayers().values():
            try:
                if lyr.customProperty(self._ROLE_PROP_KEY, "") != self._ROLE_PROP_VALUE:
                    continue
            except Exception:
                continue
            try:
                if root.findLayer(lyr.id()) is None:
                    to_remove.append(lyr.id())
            except Exception:
                continue
        if to_remove:
            try:
                project.removeMapLayers(to_remove)
            except Exception:
                for lid in to_remove:
                    try:
                        project.removeMapLayer(lid)
                    except Exception:
                        pass
