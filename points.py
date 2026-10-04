

import os

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import QMessageBox


class Points:
    """Клас для обробки точок (вузлів) з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root, xml_data=None):
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
        self.xml_data = xml_data
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
            dmt = next((dm.tag for DM in self.DMs if (dm := point.find(
                f"DeterminationMethod/{DM}")) is not None), None)
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

    def redraw_pickets_layer(self):
        """Очищує та заповнює існуючий шар 'Вузли'."""
        if not hasattr(self, 'layer') or not self.layer:

            return

        self.read_points()  # Перечитуємо точки з XML

        provider = self.layer.dataProvider()
        self.layer.startEditing()
        self.layer.deleteFeatures(self.layer.allFeatureIds())

        for xmlPoint in self.xmlPoints:
            feature = QgsFeature(self.layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(
                QgsPointXY(float(xmlPoint["Y"]), float(xmlPoint["X"]))))
            feature.setAttributes([
                xmlPoint["UIDP"], xmlPoint["PN"], xmlPoint["H"],
                xmlPoint["MX"], xmlPoint["MY"], xmlPoint["MH"],
                xmlPoint["Description"]
            ])
            provider.addFeature(feature)
        self.layer.commitChanges()

    def add_pickets_layer(self):
        """
        Створює та заповнює шар "Вузли" на основі зчитаних даних.
        """
        layer_name = "Вузли"

        existing_layer_node = self.group.findLayer(layer_name)
        if existing_layer_node:

            self.group.removeChildNode(existing_layer_node)
            QgsProject.instance().removeMapLayer(existing_layer_node.layerId())

        self.layer = QgsVectorLayer(
            f"Point?crs={self.crs_epsg}", layer_name, "memory")

        self.layer.setCustomProperty("skip_save_dialog", True)

        if not self.layer.isValid():
            QMessageBox.critical(
                None, "xml_ua", "Виникла помилка при створенні шару точок.")
            return None

        self.layer.loadNamedStyle(os.path.join(
            self.plugin_dir, "templates", "points.qml"))

        self.layer.setReadOnly(True)

        provider = self.layer.dataProvider()

        provider.addAttributes([
            QgsField("UIDP", QMetaType.Type.QString),
            QgsField("PN", QMetaType.Type.QString),
            QgsField("H", QMetaType.Type.QString),
            QgsField("MX", QMetaType.Type.QString),
            QgsField("MY", QMetaType.Type.QString),
            QgsField("MH", QMetaType.Type.QString),
            QgsField("Description", QMetaType.Type.QString)
        ])
        self.layer.updateFields()

        for xmlPoint in self.xmlPoints:
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(
                QgsPointXY(float(xmlPoint["Y"]), float(xmlPoint["X"]))))
            feature.setAttributes([
                xmlPoint["UIDP"], xmlPoint["PN"], xmlPoint["H"],
                xmlPoint["MX"], xmlPoint["MY"], xmlPoint["MH"],
                xmlPoint["Description"]
            ])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        self.group.addLayer(self.layer)
        if hasattr(self, 'xml_ua_layers'):
            self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty(
                "xml_data_object_id", id(self.xml_data))

        return self.layer
