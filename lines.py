# -*- coding: utf-8 -*-
# lines.py

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

from .common import log_msg, logFile

class PLs:
    """Клас для обробки поліліній з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root, qgis_points):
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
        self.qgis_points = qgis_points
        self.xml_lines = []
        self.qgis_lines = {}

    def read_lines(self):
        """Зчитує полілінії з XML та заповнює атрибути."""
        for line in self.root.findall(".//PL"):
            ulid = line.findtext("ULID")
            if not ulid:
                continue

            points_uidp = [p.text for p in line.findall("./Points/P")]
            length = line.findtext("Length")

            self.xml_lines.append({"ULID": ulid, "Points": points_uidp, "Length": length})
            if all(uidp in self.qgis_points for uidp in points_uidp):
                self.qgis_lines[ulid] = [self.qgis_points[uidp] for uidp in points_uidp]

    def add_lines_layer(self):
        """Створює та заповнює шар 'Полілінії'."""
        layer_name = "Полілінії"

        # --- Початок змін: Видалення існуючого шару перед створенням нового ---
        existing_layer_node = self.group.findLayer(layer_name)
        if existing_layer_node:
            log_msg(logFile, f"Шар '{layer_name}' вже існує. Видаляємо його для оновлення.")
            self.group.removeChildNode(existing_layer_node)
            QgsProject.instance().removeMapLayer(existing_layer_node.layerId())
        # --- Кінець змін ---
        layer = QgsVectorLayer(f"LineString?crs={self.crs_epsg}", layer_name, "memory")

        if not layer.isValid():
            QMessageBox.critical(None, "xml_ua", "Виникла помилка при створенні шару ліній.")
            return None

        layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "lines.qml"))
        provider = layer.dataProvider()
        # log_msg(logFile, f"Створено шар '{layer_name}' з {len(self.xml_lines)} лініями.")
        provider.addAttributes([QgsField("ULID", QVariant.String), QgsField("Length", QVariant.String)])
        layer.updateFields()

        for line_data in self.xml_lines:
            feature = QgsFeature(layer.fields())
            feature.setAttributes([line_data["ULID"], line_data["Length"]])
            if line_data["ULID"] in self.qgis_lines:
                polyline_points = [QgsPointXY(p.y(), p.x()) for p in self.qgis_lines[line_data["ULID"]]]
                feature.setGeometry(QgsGeometry.fromPolylineXY(polyline_points))
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)
        self.group.addLayer(layer)
        return layer