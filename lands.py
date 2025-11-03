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

    def __init__(self, tree_or_root, crs_epsg, group, plugin_dir, layers_root, lines_to_coords_func, xml_ua_layers_instance, xml_data=None):
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
        # --- Початок змін: Уніфікація роботи з XML-деревом ---
        # Обробляємо як кореневий елемент, так і ціле дерево
        if hasattr(tree_or_root, 'getroot'):
            self.tree = tree_or_root
            self.root = tree_or_root.getroot()
        else:
            self.root = tree_or_root
            self.tree = tree_or_root.getroottree()
        # --- Кінець змін ---
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.lines_to_coords = lines_to_coords_func
        self.xml_ua_layers = xml_ua_layers_instance
        self.xml_data = xml_data

    def _coord_to_polygon(self, coordinates):
        """Формує полігон із заданого списку координат."""
        if not coordinates:
            return QgsPolygon()
        # Координати в XML (X, Y) відповідають (Y, X) в QGIS
        line_string = QgsLineString([QgsPointXY(p.y(), p.x()) for p in coordinates])
        polygon = QgsPolygon(line_string)
        return polygon

    # --- Початок змін: Повністю перероблений метод для надійного перемальовування ---
    def redraw_lands_layer(self, layer):
        """Очищує та заповнює існуючий шар 'Угіддя'."""
        provider = layer.dataProvider()
        layer.startEditing()
        layer.deleteFeatures(layer.allFeatureIds())

        # --- Початок змін: Гарантуємо наявність поля object_shape ---
        fields = layer.fields()
        if fields.indexFromName('object_shape') == -1:
            provider.addAttributes([QgsField("object_shape", QVariant.String)])
            layer.updateFields()
        # --- Початок змін: Гарантуємо наявність поля CadastralCode ---
        if fields.indexFromName('CadastralCode') == -1:
            provider.addAttributes([QgsField("CadastralCode", QVariant.String)])
            layer.updateFields()
        # --- Кінець змін ---
        # --- Кінець змін ---

        lands_parcel_container = self.root.find(".//ParcelInfo/LandsParcel")
        if lands_parcel_container is None:
            layer.commitChanges()
            return

        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.tree)
            log_msg(logFile, "GeometryProcessor успішно створено в redraw_lands_layer.")
        except Exception as e:
            log_msg(logFile, f"Не вдалося створити GeometryProcessor в LandsParcels (redraw): {e}")
            processor = None

        # Ітеруємо по кожному LandParcelInfo
        for land_parcel_info in lands_parcel_container.findall("LandParcelInfo"):
            cadastral_code = land_parcel_info.findtext("CadastralCode")
            land_code = land_parcel_info.findtext("LandCode")
            metric_info = land_parcel_info.find("MetricInfo")
            if metric_info is None:
                continue

            size_element = metric_info.find("./Area/Size")
            size = float(size_element.text) if size_element is not None and size_element.text else None

            externals_element = metric_info.find("Externals")
            
            # Відновлюємо геометрію та object_shape
            object_shape = processor.get_object_shape_from_externals(externals_element) if processor else ""
            
            external_coords = self.lines_to_coords(externals_element.find("Boundary/Lines"), context='modify') if externals_element is not None and externals_element.find("Boundary/Lines") is not None else []
            
            internal_coords_list = []
            internals_container = externals_element.find("Internals") if externals_element is not None else None
            if internals_container is not None:
                internal_coords_list = [self.lines_to_coords(b.find('Lines'), context='modify') for b in internals_container.findall("Boundary") if b.find('Lines') is not None]

            # Створюємо полігон та додаємо його на шар
            polygon = self._create_polygon_with_holes(external_coords, internal_coords_list)
            if not polygon.isEmpty():
                feature = QgsFeature(layer.fields())
                feature.setGeometry(QgsGeometry(polygon))
                feature.setAttributes([cadastral_code, land_code, size, object_shape])
                provider.addFeature(feature)

        layer.commitChanges()
        log_msg(logFile, f"Шар '{layer.name()}' успішно перемальовано. Додано {layer.featureCount()} об'єкт(ів).")

    def _create_polygon_with_holes(self, exterior_coords, interior_coords_list):
        """Створює полігон з отворами."""
        polygon = self._coord_to_polygon(exterior_coords)
        if not polygon.isEmpty():
            for interior_coords in interior_coords_list:
                if interior_coords:
                    interior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in interior_coords])
                    polygon.addInteriorRing(interior_ring)
        return polygon
    # --- Кінець змін ---

    def add_lands_layer(self):
        """Створює та заповнює шар 'Угіддя'."""
        layer_name = "Угіддя"
        self.layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", layer_name, "memory")        
        self.layer.setCustomProperty("skip_save_dialog", True)        
        self.layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "lands_parcel.qml"))
        provider = self.layer.dataProvider()

        fields = [
            QgsField("CadastralCode", QVariant.String),
            QgsField("LandCode", QVariant.String),
            QgsField("Size", QVariant.Double),
            QgsField("object_shape", QVariant.String),
        ]
        provider.addAttributes(fields)
        self.layer.updateFields()

        # --- Зміни: Знаходимо або створюємо LandsParcel у правильному місці ---
        parcel_info = self.root.find(".//ParcelInfo")
        lands_parcel_parent = parcel_info.find("LandsParcel")
        if lands_parcel_parent is None:
            lands_parcel_parent = etree.Element("LandsParcel")
            insert_element_in_order(parcel_info, lands_parcel_parent)

        # --- Початок змін: Ініціалізація GeometryProcessor ---
        try:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.root.getroottree())
        except Exception as e:
            log_msg(logFile, f"Не вдалося створити GeometryProcessor в LandsParcels: {e}")
            processor = None
        # --- Кінець змін ---

        for lands_parcel in self.root.findall(".//LandsParcel/LandParcelInfo/MetricInfo"):
            cadastral_code = lands_parcel.findtext("../CadastralCode")
            land_code = lands_parcel.findtext("../LandCode")
            size_element = lands_parcel.find("./Area/Size")
            size = float(size_element.text) if size_element is not None and size_element.text else None

            externals_element = lands_parcel.find(".//Externals")
            if externals_element is None:
                #log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Для угіддя '{land_code}' відсутній обов'язковий розділ 'Externals'. Створено порожній об'єкт.")
                external_coords = []
            else:
                externals_lines = externals_element.find(".//Boundary/Lines")
                external_coords = self.lines_to_coords(externals_lines, context='open') if externals_lines is not None else []

            # --- Початок змін: Виправлення помилки RuntimeError при обробці отворів ---
            internal_coords_list = [self.lines_to_coords(b.find('Lines'), context='open') for b in lands_parcel.findall(".//Internals/Boundary") if b.find('Lines') is not None]

            # --- Початок змін: Генерація та збереження object_shape ---
            object_shape = ""
            if processor and externals_element is not None:
                exterior_shape = processor._get_polyline_object_shape(externals_element.find("Boundary/Lines"))
                interior_shapes = []
                internals_container = externals_element.find("Internals")
                if internals_container is not None:
                    interior_shapes = [processor._get_polyline_object_shape(internal.find("Boundary/Lines")) for internal in internals_container.findall("Boundary")]
                all_rings = [exterior_shape] + interior_shapes
                object_shape = "|".join(filter(None, all_rings))
            # --- Кінець змін ---

            polygon = self._coord_to_polygon(external_coords)
            if not polygon.isEmpty():
                for internal_coords in internal_coords_list:
                    if internal_coords:
                        # --- Початок змін: Створення QgsLineString безпосередньо ---
                        # Створюємо QgsLineString напряму, щоб уникнути проблем з володінням пам'яттю
                        # тимчасового QgsPolygon, що викликало крах QGIS.
                        interior_ring = QgsLineString([QgsPointXY(p.y(), p.x()) for p in internal_coords])
                        polygon.addInteriorRing(interior_ring)
                        # --- Кінець змін ---
            # --- Кінець змін ---

            feature = QgsFeature(self.layer.fields())
            # #log_msg(logFile, f"Геометрія угіддя перед додаванням: {polygon.asWkt()}")
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([cadastral_code, land_code, size, object_shape])
            provider.addFeature(feature)

        QgsProject.instance().addMapLayer(self.layer, False)
        layer_node = self.group.addLayer(self.layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        if self.xml_data:
            self.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))
            # #log_msg(logFile, f"Встановлено custom property на шар '{self.layer.name()}' з ID xml_data: {id(self.xml_data)}")

        return self.layer