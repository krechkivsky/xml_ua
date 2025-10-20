# -*- coding: utf-8 -*-
# lands.py

import os
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPolygon,
    QgsLineString,
    QgsPointXY,
    QgsProject,
    QgsLayerTreeLayer
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from .common import log_msg, insert_element_in_order
from .common import logFile

class LandsParcels:
    """Клас для обробки угідь з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root, lines_to_coords_func, xml_ua_layers_instance):
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
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.lines_to_coords = lines_to_coords_func
        self.xml_ua_layers = xml_ua_layers_instance

    def _coord_to_polygon(self, coordinates):
        """Формує полігон із заданого списку координат."""
        if not coordinates:
            return QgsPolygon()
        # Координати в XML (X, Y) відповідають (Y, X) в QGIS
        line_string = QgsLineString([QgsPointXY(p.y(), p.x()) for p in coordinates])
        polygon = QgsPolygon(line_string)
        return polygon

    def add_lands_layer(self):
        """Створює та заповнює шар 'Угіддя'."""
        layer_name = "Угіддя"
        layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")
        layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "lands_parcel.qml"))
        provider = layer.dataProvider()

        fields = [
            QgsField("CadastralCode", QVariant.String),
            QgsField("LandCode", QVariant.String),
            QgsField("Size", QVariant.Double),
        ]
        provider.addAttributes(fields)
        layer.updateFields()

        # --- Зміни: Знаходимо або створюємо LandsParcel у правильному місці ---
        parcel_info = self.root.find(".//ParcelInfo")
        lands_parcel_parent = parcel_info.find("LandsParcel")
        if lands_parcel_parent is None:
            lands_parcel_parent = etree.Element("LandsParcel")
            insert_element_in_order(parcel_info, lands_parcel_parent)

        for lands_parcel in self.root.findall(".//LandsParcel/LandParcelInfo/MetricInfo"):
            cadastral_code = lands_parcel.findtext("../CadastralCode")
            land_code = lands_parcel.findtext("../LandCode")
            size_element = lands_parcel.find("./Area/Size")
            size = float(size_element.text) if size_element is not None and size_element.text else None

            externals_element = lands_parcel.find(".//Externals")
            if externals_element is None:
                log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Для угіддя '{land_code}' відсутній обов'язковий розділ 'Externals'. Створено порожній об'єкт.")
                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

            internals_lines = lands_parcel.find(".//Internals/Boundary/Lines")
            internal_coords = self.lines_to_coords(internals_lines) if internals_lines is not None else []

            #`log_msg(logFile, f"Створення полігону для угіддя '{land_code}'. Зовнішніх контурів: {len(external_coords)}, Внутрішніх: {len(internal_coords)}")
            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                log_msg(logFile, "Додавання внутрішнього кільця до угіддя.")
                polygon.addInteriorRing(self._coord_to_polygon(internal_coords).exteriorRing())

            feature = QgsFeature(layer.fields())
            # log_msg(logFile, f"Геометрія угіддя перед додаванням: {polygon.asWkt()}")
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([cadastral_code, land_code, size])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)
        layer_node = self.group.addLayer(layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        return layer