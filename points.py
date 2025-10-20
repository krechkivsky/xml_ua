# -*- coding: utf-8 -*-
# points.py

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

class Points:
    """Клас для обробки точок (вузлів) з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root):
        """
        Ініціалізація об'єкта для роботи з точками.

        Args:
            root: Кореневий елемент XML-дерева.
            crs_epsg (str): EPSG-код системи координат.
            group (QgsLayerTreeGroup): Група шарів у QGIS, куди буде додано шар.
            plugin_dir (str): Шлях до директорії плагіна.
            layers_root (QgsLayerTreeGroup): Кореневий вузол дерева шарів QGIS.
        """
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.xmlPoints = []
        self.qgisPoints = {}
        self.DMs = ['Survey', 'GPS', 'Digitization', 'Photogrammetry']

    def read_points(self):
        """
        Зчитує точки з XML та заповнює атрибути xmlPoints та qgisPoints.
        """
        self.xmlPoints = []
        self.qgisPoints = {}

        for point in self.root.findall(".//PointInfo/Point"):
            uidp = point.findtext("UIDP")
            pn = point.findtext("PN")
            dmt = next((dm.tag for DM in self.DMs if (dm := point.find(f"DeterminationMethod/{DM}")) is not None), None)
            x = point.findtext("X")
            y = point.findtext("Y")
            h = point.findtext("H")
            mx = point.findtext("MX")
            my = point.findtext("MY")
            mh = point.findtext("MH")
            description = point.findtext("Description")

            self.xmlPoints.append({
                "UIDP": uidp, "PN": pn, "DeterminationMethod": dmt,
                "X": x, "Y": y, "H": h,
                "MX": mx, "MY": my, "MH": mh,
                "Description": description
            })

            if uidp and x and y:
                self.qgisPoints[uidp] = QgsPointXY(float(x), float(y))

    def add_pickets_layer(self):
        """
        Створює та заповнює шар "Вузли" на основі зчитаних даних.
        """
        layer_name = "Вузли"

        # Перевірка, чи шар вже існує в групі
        existing_layer_node = self.group.findLayer(layer_name)
        if existing_layer_node:
            log_msg(logFile, f"Шар '{layer_name}' вже існує. Видаляємо його для оновлення.")
            self.group.removeChildNode(existing_layer_node)
            QgsProject.instance().removeMapLayer(existing_layer_node.layerId())

        layer = QgsVectorLayer(f"Point?crs={self.crs_epsg}", layer_name, "memory")

        if not layer.isValid():
            QMessageBox.critical(None, "xml_ua", "Виникла помилка при створенні шару точок.")
            return None

        layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "points.qml"))
        
        provider = layer.dataProvider()
        # log_msg(logFile, f"Створено шар '{layer_name}' з {len(self.xmlPoints)} точками.")
        provider.addAttributes([
            QgsField("UIDP", QVariant.String),
            QgsField("PN", QVariant.String),
            QgsField("H", QVariant.String),
            QgsField("MX", QVariant.String),
            QgsField("MY", QVariant.String),
            QgsField("MH", QVariant.String),
            QgsField("Description", QVariant.String)
        ])
        layer.updateFields()

        for xmlPoint in self.xmlPoints:
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(xmlPoint["Y"]), float(xmlPoint["X"]))))
            feature.setAttributes([
                xmlPoint["UIDP"], xmlPoint["PN"], xmlPoint["H"],
                xmlPoint["MX"], xmlPoint["MY"], xmlPoint["MH"],
                xmlPoint["Description"]
            ])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)
        self.group.addLayer(layer)
        return layer