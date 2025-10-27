# -*- coding: utf-8 -*-
# adjacents.py

import os
from qgis.core import (
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

from .common import log_msg, insert_element_in_order
from .common import logFile

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
        natural_person = adjacent_element.find(".//Proprietor/NaturalPerson/FullName")
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
            # Аналогічно, виходимо, якщо розділу немає
            #log_msg(logFile, "Розділ 'AdjacentUnits' відсутній в XML. Шар 'Суміжники' не буде створено/оновлено.")
            return None

        layer_name = "Суміжники"
        # Видаляємо старий шар, якщо він існує, щоб уникнути дублювання
        layers_to_remove = [child.layerId() for child in self.group.children() if child.name() == layer_name]
        if layers_to_remove:
            QgsProject.instance().removeMapLayers(layers_to_remove)
            #log_msg(logFile, f"Старий шар '{layer_name}' знайдено для видалення перед створенням нового.")


        self.layer = QgsVectorLayer(f"LineString?crs={self.crs_epsg}", layer_name, "memory")
        self.layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "adjacent.qml"))
        # --- Початок змін: Встановлення прапорця тимчасового шару ---
        # Повідомляємо QGIS, що цей шар не потрібно зберігати при закритті проекту.
        self.layer.setCustomProperty("skip_save_dialog", True)
        # --- Кінець змін ---
        provider = self.layer.dataProvider()

        fields = [
            QgsField("CadastralNumber", QVariant.String),
            QgsField("Proprietor", QVariant.String),
        ]
        provider.addAttributes(fields)
        self.layer.updateFields()

        for adjacent in adjacents_parent.findall(".//AdjacentUnitInfo"):
            cadastral_number = adjacent.findtext(".//CadastralNumber")
            proprietor = self._get_proprietor_name(adjacent)
            boundary_element = adjacent.find(".//AdjacentBoundary/Lines")
            if boundary_element is not None:
                try:
                    boundary_coords = self.xml_ua_layers.lines_element2polyline(boundary_element)
                    if boundary_coords and len(boundary_coords) >= 2:
                        line_string = QgsLineString([QgsPointXY(p.y(), p.x()) for p in boundary_coords])
                        feature = QgsFeature(self.layer.fields())
                        feature.setGeometry(QgsGeometry(line_string))
                        feature.setAttributes([cadastral_number, proprietor])
                        provider.addFeature(feature)
                except ValueError as e:
                    # #log_msg(logFile, f"Помилка при обробці суміжника {cadastral_number}: {e}")
                    continue

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))
            # #log_msg(logFile, f"Встановлено custom property на шар '{self.layer.name()}' з ID xml_data: {id(self.xml_data)}")

        return self.layer