

import os
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsLayerTreeLayer
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox


class PLs:
    """Клас для обробки поліліній з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root, qgis_points, xml_data=None):
        """
        Ініціалізація об'єкта для роботи з полілініями.

        Args:
            root: Кореневий елемент XML-дерева.
            crs_epsg (str): EPSG-код системи координат.
            group (QgsLayerTreeGroup): Група шарів у QGIS, куди буде додано шар.
            plugin_dir (str): Шлях до директорії плагіна.
            layers_root (QgsLayerTreeGroup): Кореневий вузол дерева шарів QGIS.
            qgis_points (dict): Словник зчитаних точок (вузлів).
        """
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.xml_data = xml_data
        self.qgis_points = qgis_points
        self.xml_lines = []
        self.qgis_lines = {}

    def read_lines(self):
        """Зчитує полілінії з XML та заповнює атрибути."""

        self.xml_lines.clear()
        self.qgis_lines.clear()

        for line in self.root.findall(".//PL"):
            ulid = line.findtext("ULID")
            if not ulid:
                continue

            points_uidp = [p.text for p in line.findall("./Points/P")]
            length = line.findtext("Length")

            self.xml_lines.append(
                {"ULID": ulid, "Points": points_uidp, "Length": length})
            if all(uidp in self.qgis_points for uidp in points_uidp):
                self.qgis_lines[ulid] = [self.qgis_points[uidp]
                                         for uidp in points_uidp]

    def redraw_lines_layer(self):
        """Очищує та заповнює існуючий шар 'Полілінії'."""
        if not hasattr(self, 'layer') or not self.layer:

            return

        self.read_lines()  # Перечитуємо лінії з XML

        provider = self.layer.dataProvider()
        self.layer.startEditing()
        self.layer.deleteFeatures(self.layer.allFeatureIds())

        for line_data in self.xml_lines:
            feature = QgsFeature(self.layer.fields())
            feature.setAttributes([line_data["ULID"], line_data["Length"]])
            if line_data["ULID"] in self.qgis_lines:
                polyline_points = [QgsPointXY(p.y(), p.x())
                                   for p in self.qgis_lines[line_data["ULID"]]]
                feature.setGeometry(
                    QgsGeometry.fromPolylineXY(polyline_points))
            provider.addFeature(feature)
        self.layer.commitChanges()

    def add_lines_layer(self):
        """Створює та заповнює шар 'Полілінії'."""
        layer_name = "Полілінії"

        existing_layer_node = self.group.findLayer(layer_name)
        if existing_layer_node:

            self.group.removeChildNode(existing_layer_node)
            QgsProject.instance().removeMapLayer(existing_layer_node.layerId())

        self.layer = QgsVectorLayer(
            f"LineString?crs={self.crs_epsg}", layer_name, "memory")

        self.layer.setCustomProperty("skip_save_dialog", True)

        if not self.layer.isValid():
            QMessageBox.critical(
                None, "xml_ua", "Виникла помилка при створенні шару ліній.")
            return None

        self.layer.loadNamedStyle(os.path.join(

            self.plugin_dir, "templates", "lines.qml"))

        self.layer.setReadOnly(True)

        provider = self.layer.dataProvider()

        provider.addAttributes(
            [QgsField("ULID", QVariant.String), QgsField("Length", QVariant.String)])
        self.layer.updateFields()


        for line_data in self.xml_lines:
            feature = QgsFeature(self.layer.fields())
            feature.setAttributes([line_data["ULID"], line_data["Length"]])
            if line_data["ULID"] in self.qgis_lines:
                polyline_points = [QgsPointXY(p.y(), p.x())
                                   for p in self.qgis_lines[line_data["ULID"]]]
                feature.setGeometry(
                    QgsGeometry.fromPolylineXY(polyline_points))
            provider.addFeature(feature)


        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        if hasattr(self, 'xml_ua_layers'):
            self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
