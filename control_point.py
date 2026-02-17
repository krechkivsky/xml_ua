import os

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox


class ControlPoint:
    """
    Обробник шару "Закріплені вузли" (MetricInfo/ControlPoint/P).

    Шар є похідним: він відображає точки з PointInfo/Point, UIDP яких перелічені
    у MetricInfo/ControlPoint/P.
    """

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root, points_handler=None, xml_data=None):
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.points_handler = points_handler
        self.xml_data = xml_data
        self.layer = None

    def _get_control_point_uidps(self):
        uidps = []
        try:
            for p_el in self.root.findall(".//MetricInfo/ControlPoint/P"):
                uidp = (p_el.text or "").strip()
                if uidp:
                    uidps.append(uidp)
        except Exception:
            return []

        return list(dict.fromkeys(uidps))

    def redraw_layer(self):
        if not self.layer:
            return

        if self.points_handler:
            try:
                self.points_handler.read_points()
            except Exception:
                pass

        uidps = self._get_control_point_uidps()
        xml_points = getattr(self.points_handler, "xmlPoints", []) if self.points_handler else []
        point_by_uidp = {p.get("UIDP"): p for p in xml_points if p.get("UIDP")}

        provider = self.layer.dataProvider()
        self.layer.startEditing()
        self.layer.deleteFeatures(self.layer.allFeatureIds())

        for uidp in uidps:
            xml_point = point_by_uidp.get(uidp)
            if not xml_point:
                continue
            x = xml_point.get("X")
            y = xml_point.get("Y")
            if not x or not y:
                continue
            try:
                feature = QgsFeature(self.layer.fields())

                feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(y), float(x))))
                feature.setAttributes([uidp])
                provider.addFeature(feature)
            except Exception:
                continue

        self.layer.commitChanges()

    def add_control_points_layer(self):
        layer_name = "Закріплені вузли"

        existing_layer_node = self.group.findLayer(layer_name)
        if existing_layer_node:
            self.group.removeChildNode(existing_layer_node)
            QgsProject.instance().removeMapLayer(existing_layer_node.layerId())

        self.layer = QgsVectorLayer(f"Point?crs={self.crs_epsg}", layer_name, "memory")
        self.layer.setCustomProperty("skip_save_dialog", True)

        if not self.layer.isValid():
            QMessageBox.critical(None, "xml_ua", "Виникла помилка при створенні шару 'Закріплені вузли'.")
            return None

        style_path = os.path.join(self.plugin_dir, "templates", "control_point.qml")
        if os.path.exists(style_path):
            self.layer.loadNamedStyle(style_path)

        self.layer.setReadOnly(True)

        provider = self.layer.dataProvider()
        provider.addAttributes([QgsField("UIDP", QVariant.String)])
        self.layer.updateFields()

        QgsProject.instance().addMapLayer(self.layer, False)
        self.group.addLayer(self.layer)

        if self.xml_data:
            self.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))

        self.redraw_layer()
        return self.layer

