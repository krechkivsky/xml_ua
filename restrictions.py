# -*- coding: utf-8 -*-
# restrictions.py

import os
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPolygon,
    QgsLineString,
    QgsPointXY,
    QgsProject
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from .common import log_msg, insert_element_in_order
from .common import logFile

class Restrictions:
    """Клас для обробки даних про обмеження з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, lines_to_coords_func, xml_ua_layers_instance):
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

    def _coord_to_polygon(self, coordinates):
        """Формує полігон із заданого списку координат."""
        if not coordinates:
            return QgsPolygon()
        # Координати в XML (X, Y) відповідають (Y, X) в QGIS
        line_string = QgsLineString([QgsPointXY(p.y(), p.x()) for p in coordinates])
        polygon = QgsPolygon(line_string)
        return polygon

    def redraw_restrictions_layer(self, layer):
        """Очищує та заповнює існуючий шар 'Обмеження'."""
        provider = layer.dataProvider()
        layer.startEditing()
        layer.deleteFeatures(layer.allFeatureIds())

        restrictions_parent = self.root.find(".//ParcelInfo/Restrictions")
        if restrictions_parent is None:
            layer.commitChanges()
            return

        for restriction in restrictions_parent.findall(".//RestrictionInfo"):
            restriction_code = restriction.findtext(".//RestrictionCode")
            restriction_name = restriction.findtext(".//RestrictionName")
            start_date = restriction.findtext(".//RestrictionTerm/Time/StartDate")
            expiration_date = restriction.findtext(".//RestrictionTerm/Time/ExpirationDate")

            externals_lines = restriction.find(".//Externals/Boundary/Lines")
            external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

            internals_lines = restriction.find(".//Internals/Boundary/Lines")
            internal_coords = self.lines_to_coords(internals_lines) if internals_lines is not None else []

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                polygon.addInteriorRing(self._coord_to_polygon(internal_coords).exteriorRing())

            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([restriction_code, restriction_name, start_date, expiration_date])
            provider.addFeature(feature)
        layer.commitChanges()

    def add_restrictions_layer(self):
        """Створює та заповнює шар 'Обмеження'."""
        parcel_info = self.root.find(".//ParcelInfo")
        restrictions_parent = parcel_info.find("Restrictions")
        if restrictions_parent is None:
            # Аналогічно, виходимо, якщо розділу немає
            log_msg(logFile, "Розділ 'Restrictions' відсутній. Шар 'Обмеження' не буде створено.")
            return None

        layer_name = "Обмеження"
        layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")
        layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "restriction.qml"))
        provider = layer.dataProvider()

        fields = [
            QgsField("RestrictionCode", QVariant.String),
            QgsField("RestrictionName", QVariant.String),
            QgsField("StartDate", QVariant.String),
            QgsField("ExpirationDate", QVariant.String),
        ]
        provider.addAttributes(fields)
        layer.updateFields()

        for restriction in restrictions_parent.findall(".//RestrictionInfo"):
            restriction_code = restriction.findtext(".//RestrictionCode")
            restriction_name = restriction.findtext(".//RestrictionName")
            start_date = restriction.findtext(".//RestrictionTerm/Time/StartDate")
            expiration_date = restriction.findtext(".//RestrictionTerm/Time/ExpirationDate")

            externals_element = restriction.find(".//Externals")
            if externals_element is None:
                log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Для обмеження '{restriction_code}' відсутній обов'язковий розділ 'Externals'. Створено порожній об'єкт.")
                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

            internals_lines = restriction.find(".//Internals/Boundary/Lines")
            internal_coords = self.lines_to_coords(internals_lines) if internals_lines is not None else []

            polygon = self._coord_to_polygon(external_coords)
            if internal_coords:
                polygon.addInteriorRing(self._coord_to_polygon(internal_coords).exteriorRing())

            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([restriction_code, restriction_name, start_date, expiration_date])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)
        layer_node = self.group.addLayer(layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        return layer