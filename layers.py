# -*- coding: utf-8 -*-

import os
import xml.etree.ElementTree as ET

from qgis.core import Qgis
from qgis.core import QgsLayerTreeGroup

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.utils import iface


from qgis.core import QgsProject
from qgis.core import QgsLineString
from qgis.core import QgsGeometry
from qgis.core import QgsPolygon
from qgis.core import QgsMultiPolygon
from qgis.core import QgsLayerTreeLayer
from qgis.core import QgsVectorLayer
from qgis.core import QgsField
from qgis.core import QgsFeature
from qgis.core import QgsPointXY
from qgis.core import QgsEditorWidgetSetup

from qgis.gui import QgisInterface

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QInputDialog

from lxml import etree as ET
#from xml.etree import ElementTree as ET

from .common import logFile
from .common import log_msg
from .common import log_calls
from .common import category_map
from .common import purpose_map
from .common import code_map
from .common import parcel_field2path_dict
from .common import area_determination_map

class xmlUaLayers:
    # Встановлюється які шари буде містити графічне представлення документа xml
    # А також шари які пов'язані з графічними елементами але самі не мають графічного представлення
    # Наприклад власники, орендарі, бенефіціари, документи, Склад технічної документації

    # формуються Поля даних, аліаси та знаходяться значення полів у документі xml
    # 
    


    # це атрибут класу він збільшується на 1 в конструкторі
    # і таким чином формує унікальний ідентифікатор кожного
    # екземпляру класу, який створюється для кожного xml
    _id_counter = 0
    
    def __init__(self, 
                xmlFilePath = "", 
                tree = None, 
                plugin=None):

        # xmlFilePath - для формування назви групи шарів
        # tree        - розпарсене дерево xml
        # plugin      _ для підключення обробника редагування геометрії

        # __init__  виклик конструктора з dockwidget.py:process_action_open
        # обох викликах tree розпарсений
        
        self.cleanup()

        self.plugin = plugin  

        xmlUaLayers._id_counter += 1

        # ✨ унікальний ідентифікатор екземпляра класу
        self.id = xmlUaLayers._id_counter

        # log_calls(logFile, f"Новий xmlUaLayers з id {str(self.id)}")

        # Для подавлення повторних форм вводу при відміні введеного 
        # значення -> проблема виникла при зміні способу
        # визначення площі ділянки на переобчислення з МСК
        # 🚩
        self.block_attribute_handling = False

        # Індикатор зміни даних, розпарсених з xml
        #✔️ 2025.04.19 поки спільний для тексту і геометрії
        # 🚩
        self.xml_data_changed = False

        # Словник для зберігання кольорів шарів
        self.layer_colors = {}

        # ініціюємо список назв шарів QGIS
        self.layers = QgsProject.instance().mapLayers().values()

        # отримання кореня дерева шарів
        self.layers_root = QgsProject.instance().layerTreeRoot()
        
        self.xmlFilePath: str = xmlFilePath
        self.plugin_dir = os.path.dirname(__file__)
        
        self.fileNameNoExt: str = os.path.splitext(os.path.basename(xmlFilePath))[0]

        # генеруємо унікальне ім'я групи шарів, в яку будуть поміщені шари xml  
        self.group_name = self.generate_group_name(self.fileNameNoExt)

        # Дерево xml
        self.tree = ET.parse(self.xmlFilePath)
        # Корінь дерева xml
        self.root = self.tree.getroot()

        self.project = QgsProject.instance()
        self.crs = self.project.crs()
        self.crsEpsg = self.crs.authid()
        self.group = None
        self.xmlPoints: list = []
        self.qgisPoints: dict = {}
        self.qgisLines: dict = {}
        self.xmlLines: list = []
        self.ULIDs: list = []
        self.qgisLinesXML: dict = {}
        self.DMs: list = ['Survey','GPS','Digitization','Photogrammetry']
        self.added_layers = []

        self.create_group()

        self.read_points()
        self.read_lines()

        self.add_pickets()
        self.add_lines()

        self.add_zone()
        self.add_quartal()
        self.add_parcel()
        self.add_lands()
        self.add_leases()
        self.add_subleases()
        self.add_restrictions()

        self.add_adjacents()
    def generate_group_name(self, base_name):

        """
        Формує назву групи на основі базової назви, додаючи суфікс, якщо група з такою назвою вже існує.
        """

        # log_calls(logFile, f"base_name = {base_name}")
        
        group_name = base_name

        existing_groups = [group.name() for group in self.layers_root.findGroups()]

        if group_name not in existing_groups:
            # log_calls(logFile, f"group_name = {group_name}")
            return group_name

        suffix = 1
        while f"{base_name}#{suffix}" in existing_groups:
            suffix += 1

        group_name = f"{base_name}#{suffix}"
        log_msg(logFile, f"group_name = {group_name}")
        return group_name

    def cleanup(self):
        """
        Очищує ресурси, пов'язані з попереднім екземпляром,
        щоб уникнути дублювання при перезавантаженні плагіна.
        """
        # Спочатку видаляємо групу. Це також видалить усі дочірні вузли шарів з дерева.
        # Шари, що були в групі, автоматично видаляються з проекту.
        if hasattr(self, 'group') and self.group:
            # Перевіряємо, чи вузол все ще існує в дереві, перш ніж видаляти
            if self.layers_root.findGroup(self.group.name()):
                 self.layers_root.removeChildNode(self.group)
            self.group = None

        # Очищуємо список доданих шарів, оскільки вони вже видалені разом з групою.
        if hasattr(self, 'added_layers'):
            self.added_layers = []
    def create_group(self):
        """
        Creates a group for XML layers, restricting renaming and subgroup addition.
        This method performs the following actions:
        - Creates a new group in the layer tree with the specified group name.
        - Sets the group to be read-only, preventing renaming or adding subgroups.
        - Updates the list of layers and the root of the layer tree.
        - Moves the newly created group to the top of the layer tree.
        Returns:
            None
        """
        # log_calls(logFile)
        self.group = self.layers_root.addGroup(self.group_name)
        cloned_group = self.group.clone()
        self.layers_root.removeChildNode(self.group)
        self.layers_root.insertChildNode(0, cloned_group)
        self.group = cloned_group

        # оновлення шарів та кореня дерева шарів
        self.layers = QgsProject.instance().mapLayers().values()
        self.layers_root = QgsProject.instance().layerTreeRoot()

        return
    def read_points(self):
        """
        Imports points from an XML structure and stores them in two attributes: 
        `xmlPoints` and `qgisPoints`.
        The method processes each point found in the XML structure under the path 
        ".//PointInfo/Point".
        It extracts various attributes for each point, including 
        UIDP, PN, DeterminationMethod, X, Y, H, MX, MY, MH, and Description.
        These attributes are stored in a dictionary which is 
        appended to the `xmlPoints` list.
        Additionally, the method creates a `QgsPointXY` object for each point 
        using the X and Y coordinates and stores it in the `qgisPoints` dictionary 
        with UIDP as the key.

        Don't create any layer.
        
        Attributes:
            xmlPoints (list): A list of dictionaries, each containing point 
            attributes extracted from the XML.
            qgisPoints (dict): A dictionary mapping UIDP to `QgsPointXY` 
            objects representing the points.
        
        Returns:
            None
        """

        # log_calls(logFile)

        self.xmlPoints = []
        self.qgisPoints = {}

        for point in self.root.findall(".//PointInfo/Point"):
            uidp = point.find("UIDP").text if point.find("UIDP") is not None else None
            pn = point.find("PN").text if point.find("PN") is not None else None
            for DM in self.DMs:
                dm = point.find("DeterminationMethod/" + DM)
                if dm is None :
                    log_calls(logFile, " dmt: " + 'NoneType')
                    pass
                else:
                    dmt = dm.tag
                    # log_calls(logFile, " dmt: '" + dmt + "'")
                break
            x = point.find("X").text if point.find("X") is not None else None
            y = point.find("Y").text if point.find("Y") is not None else None
            h = point.find("H").text if point.find("H") is not None else None
            mx = point.find("MX").text if point.find("MX") is not None else None
            my = point.find("MY").text if point.find("MY") is not None else None
            mh = point.find("MH").text if point.find("MH") is not None else None
            description = point.find("Description").text if point.find("Description") is not None else None

            self.xmlPoints.append({
                "UIDP": uidp,
                "PN": pn,
                "DeterminationMethod": dmt,
                "X": x,
                "Y": y,
                "H": h,
                "MX": mx,
                "MY": my,
                "MH": mh,
                "Description": description
            })


            self.qgisPoints[uidp] = QgsPointXY(float(x), float(y))

        # log_calls(logFile, "xmlPoints")
        # log_calls(logFile, "qgisPoints")

        return
    def add_pickets(self):
        """
        Imports picket points from XML data and adds them as a new layer to the QGIS project.
        Ensures the layer "Пікети" is added only once to the specified group.
        """
        # log_calls(logFile)
        layer_name = "Пікети"

        # Check if layer already exists in the group
        group = self.layers_root.findGroup(self.group_name)
        existing_layer = None
        if group:
            for child in group.children():
                if isinstance(child, QgsLayerTreeLayer) and child.name() == layer_name:
                    existing_layer = child.layer()
                    break

        if existing_layer:
            log_msg(logFile, f"Шар '{layer_name}' вже існує в групі '{self.group_name}'.")
            return  # Layer already exists in the group; do nothing

        self.removeLayer(layer_name)  # Remove from root if it's there

        layer = QgsVectorLayer("Point?crs=" + self.crsEpsg, layer_name, "memory")

        if layer.isValid():
            layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/points.qml")
            QgsProject.instance().addMapLayer(layer, False)  # Add to project, but not to tree yet


            if group is None: # ensure group exist
                group = self.layers_root.addGroup(self.group_name)
            
            layer_node = group.addLayer(layer) # Add directly to the group only once
            self.added_layers.append(layer_node)

        else:
            QMessageBox.critical(self, "xml_ua", "Виникла помилка при створенні шару точок.")
            return

        provider = layer.dataProvider()

        provider.addAttributes([
            QgsField("UIDP", QVariant.String),
            QgsField("PN", QVariant.String),
            QgsField("H", QVariant.String),
            QgsField("MX", QVariant.String),
            QgsField("MY", QVariant.String),
            QgsField("MH", QVariant.String),
            QgsField("Description", QVariant.String)])
        layer.updateFields()

        for xmlPoint in self.xmlPoints:
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(xmlPoint["Y"]), float(xmlPoint["X"]))))
            feature.setAttributes([
                xmlPoint["UIDP"],
                xmlPoint["PN"],
                xmlPoint["H"],
                xmlPoint["MX"],
                xmlPoint["MY"],
                xmlPoint["MH"],
                xmlPoint["Description"]])
            provider.addFeature(feature)

        return
    def read_lines(self):
        """

        The method read_lines is defined but not called anywhere in the class. 

        :return: None
        :rtype: None
        """

        # log_calls(logFile)

        self.qgisLines = {}
        self.xmlLines = []

        logstr = ''
        for line in self.root.findall(".//PL"):

            ulid = line.find("ULID").text
            if ulid is None: continue
            points_uidp = [p.text for p in line.findall(".//P")]
            logstr += '\n\t "' + ulid + '" ' + str(points_uidp)

            length = line.find("Length").text if line.find("Length") is not None else None
            self.xmlLines.append({
                "ULID": ulid,
                "Points": points_uidp,
                "Length": length
            })

            self.qgisLines[ulid] = [self.qgisPoints[uidp] for uidp in points_uidp ]

        # log_msg(logFile, "\n    ULID [Point list]:" + logstr )

        return
    def add_zone(self):
        """
        Imports zones from the XML file and adds them as a new layer to the QGIS project,
        ensuring the layer is added only once and at the top of the specified group.
        If the layer already exists, it's removed and recreated.
        """        
        
        # log_calls(logFile)
        layer_name = "Кадастрова зона"

        # Check if the layer already exists in the group
        group = self.layers_root.findGroup(self.group_name)  # Corrected to use findGroup
        if group is None:
            group = self.layers_root.addGroup(self.group_name)
            log_calls(logFile, f"Група '{self.group_name}' створена.")
        else:
            # log_calls(logFile, f"Група '{self.group_name}' знайдена.")
            pass

        # Check if the layer already exists in the group
        existing_layer = None

        for child in group.children():
            if isinstance(child, QgsLayerTreeLayer) and child.name() == layer_name:
                existing_layer = child.layer()
                break

        # log_calls(logFile, f"existing_layer = {existing_layer}")
        # log_calls(logFile, f"self.group_name = {self.group_name}")

        # Remove the existing layer if found
        if existing_layer:
            self.removeLayer(layer_name, self.group_name) # remove existing layer from group



        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, layer_name, "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/zone.qml")
        # log_calls(logFile, f"layer = {layer}")


        if not layer.isValid():
            QMessageBox.critical(self, "xml_ua", "Виникла помилка при створенні шару зон.")
            return

        layer_provider = layer.dataProvider()
        layer_provider.addAttributes([
            QgsField("CadastralZoneNumber", QVariant.String)
        ])
        layer.updateFields()

        zone_ne = self.root.find(".//CadastralZoneInfo/CadastralZoneNumber")
        zone_id = zone_ne.text if zone_ne is not None else None  # Handle potential missing element

        for zone in self.root.findall(".//CadastralZoneInfo"):
            externals_element = zone.find(".//Externals/Boundary/Lines")
            external_coords = self.linesToCoordinates(externals_element) if externals_element is not None else []

            internals_element = zone.find(".//Internals/Boundary/Lines")
            internal_coords_list = [self.linesToCoordinates(internals_element)] if internals_element is not None else []

            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)

            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([zone_id])
            layer_provider.addFeature(feature)

        # root.addLayer(layer)  # No need for addMapLayer anymore

        # Add the layer to the project but *not* directly to the layer tree:
        QgsProject.instance().addMapLayer(layer, False) 


        # # Move the layer to the top of its group (after adding it to the root)        
        # root = QgsProject.instance().layerTreeRoot()
        # tree_layer = root.findLayer(layer.id())  # Retrieve the tree layer
        # if tree_layer:
        #     group.insertChildNode(0, tree_layer) # Now insert it at the top
        # else:
        #     log_msg(logFile, f"Error: Could not find tree layer for '{layer_name}'")

        # # Ensure the group exists:

        # log_calls(logFile, f"group = {group}")
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # # Add the layer *only* to the group:
        layer_node = group.addLayer(layer)  # Use addLayer directly on the group

        self.last_to_first(group)

        self.added_layers.append(layer_node)
        return
    def last_to_first(self, group):
        """Moves the last child node of a layer tree group to the first position."""
        if group is None:
            return

        children = group.children()  # Get the list of children
        child_count = len(children)  # Get the number of children

        if child_count < 2:
            return

        last_child = children[-1]  # Access the last child using negative indexing
        cloned_last_child = last_child.clone()

        group.insertChildNode(0, cloned_last_child)
        group.removeChildNode(last_child)
    def linesToCoordinates(self, lines_element):
        """ Формує список координат замкненого полігону на основі ULID ліній 
            і їх точок.

            Parameters:
                lines_element (xml.etree.ElementTree.Element): 

            Returns:
                list: Список координат замкненого полігону.
        """

        # log_calls(logFile)
        
        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        # Зчитати всі ULID ліній
        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//Line"):
            i += 1
            ulid = line.find("ULID").text
            # logstr += '\n\t' + ulid + '. '+ str(line)
            logstr += '\n\t' + ulid + '. '

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
            elif ulid:
                raise ValueError(f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError("Лінія не містить атрибуту унікального ідентифікатора.")
        # log_calls(logFile, "\n\t   ULID:" + logstr)

        # Формуємо замкнений полігон
        if not lines:
            return []

        polygon_coordinates = []
        used_lines = set()
        current_line = lines[0]
        polygon_coordinates.extend(current_line[1])  # Додати точки першої лінії
        used_lines.add(current_line[0])

        while len(used_lines) < len(lines):
            # Пошук наступної лінії, що з'єднується
            for ulid, coords in lines:
                if ulid in used_lines:
                    continue
                if coords[0] == polygon_coordinates[-1]:  # З'єднання кінця попередньої лінії з початком наступної
                    polygon_coordinates.extend(coords[1:])
                    used_lines.add(ulid)
                    break
                elif coords[-1] == polygon_coordinates[-1]:  # З'єднання кінця попередньої лінії з кінцем наступної
                    polygon_coordinates.extend(reversed(coords[:-1]))
                    used_lines.add(ulid)
                    break
            else:
                raise ValueError("Неможливо сформувати замкнений полігон — деякі лінії не з'єднуються.")

        # Замикання полігону
        if polygon_coordinates[0] != polygon_coordinates[-1]:
            polygon_coordinates.append(polygon_coordinates[0])

        return polygon_coordinates
    def coordToPolygon(self, coordinates):
        """
        Формує полігон із заданого списку координат.
        """

        # log_calls(logFile)

        logstr = ''
        i = 0
        for point in coordinates:
            i += 1
            logstr += f"\n\t {str(i)}. {point.x():.2f}, {point.y():.2f}"
        # log_calls(logFile, "\n\tcoordinates: " + logstr)

        line_string = QgsLineString([QgsPointXY(y, x) for x, y in coordinates])

        polygon = QgsPolygon()
        polygon.setExteriorRing(line_string)  # Додавання зовнішнього кільця
        return polygon


    def add_parcel(self):
        # Тут фомується шар Ділянка, додається у групу
        # Тут знаходяться з xml документа дані про ділянку
        # Даються назви полям і їх аліасам, знаходяться їх значення в документа Xml


        # перевірити кількість розділів ParcelInfo
        # якщо їх кілька - потрібно вибрати якийсь один
        # їх має бути лише один, якщо документ XML описує одну технічну документацію
        # бо розділ TechnicalDocumentationInfo є обов'язковим підрозділом ParcelInfo
        parcel_infos = self.root.findall(".//Parcels/ParcelInfo")
        
        if len(parcel_infos) == 0:
            log_msg(logFile, "У {self.xmlFilePath} відсутній елемент ParcelInfo")
            return False
        else:
            log_msg(logFile, f"У {self.xmlFilePath} знайдено {len(parcel_infos)} розділів ParcelInfo. Використовується перший.")
            # Можна додати діалог вибору користувачем
            # Але поки що беремо перший
            parcel_info = parcel_infos[0]
            metric_info = parcel_info.find("ParcelMetricInfo")
            if metric_info is None:
                log_msg(logFile, "Відсутній елемент ParcelMetricInfo у першому ParcelInfo")
                return False

        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, "Ділянка", "memory")
        # Накладання стилю QML
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/parcel.qml")
        # Отримання провайдера даних шару
        layer_provider = layer.dataProvider()
        # region📌 Обробка сигналів QGIS-інтерфейсу
        # обробники сигналів шару Ділянка
        def on_attributes_committed(feature_ids):
            """
            Обробник сигналу committedAttributesChanged.

            Args:
                feature_ids: Список ID фіч, атрибути яких були змінені.
            """
            log_calls(logFile, f"Змінено атрибути фіч з ID {feature_ids}.")
            self.layer_modified = True
            QMessageBox.information(None, "xml_ua", f"Змінено атрибути фіч з ID {feature_ids}.")    

            # Тут ви можете додати код для збереження дерева XML у файл.
            # Наприклад:
            # save_xml_tree_to_file(self.xml_tree, self.xml_file_path)
        def on_feature_added(feature):
            """Обробник сигналу про додавання об'єктів."""
            self.layer_modified = True
            self.show_message("on_features_added", f"Додано об'єкти: {feature}")
        def on_feature_deleted(feature):
            """Обробник сигналу про видалення об'єктів."""
            self.layer_modified = True
            self.show_message("on_features_deleted", f"Видалено об'єкти з ID: {feature}")
        def on_geometry_changed(feature_id, geometry):
            """Обробник сигналу про зміну геометрії об'єкта."""
            self.layer_modified = True
            self.show_message("on_geometry_changed", f"Геометрію об'єкта з ID {feature_id} змінено.")
        # підключення обробників сигналів шару
        #✔️ 2025.05.19 editingStopped
        layer.editingStopped.connect(self.on_editing_stopped)
        layer.featureAdded.connect(on_feature_added)
        layer.featureDeleted.connect(on_feature_deleted)
        # layer.geometryChanged.connect(on_geometry_changed)
        # endregion
        
        # region📌 Обробка сигналів форми атрибутів Ділянки
        # Підписка на сигнал layer про зміну його атрибутів 
        # сигнал шару містить лише id форми, id поля, нове значення
        # сигнал шару НЕ містить НАВІТЬ об'єкт layer✨
        # сигнал підключається у коді класу ->
        # і його отримає кожен✨ екземпляр класу у купі
        # Не можливо встановити у коді у якому екземплярі xmlUaLayers
        # створено layer, бо отримуємо перевірку self.id == self.id 
        # Тому для передачі layer(parcel) і self.id(xmlUaLayers)  
        # 1) "заморожуємо" self.id xmlUaLayers:
        layer.setCustomProperty("xml_layer_id", self.id)
        # 2) вносимо layer у контекст (__closure__) λ 
        # 3) встановлюємо у якості обробника не сам обробник а λ: 
        layer.attributeValueChanged.connect(lambda fid, idx, val, l=layer: self.handle_parcel_attribute_change(l, fid, idx, val))
        # endregion
        # endregion
        # region📌 Опис полів шару Ділянка
        fields = [
            # 1 
            QgsField("ParcelID", QVariant.String),
            # 2
            QgsField("Description", QVariant.String),
            # 3
            QgsField("AreaSize", QVariant.Double),
            # 4
            QgsField("AreaUnit", QVariant.String),
            # 5
            QgsField("DeterminationMethod", QVariant.String),
            # 6
            QgsField("Region", QVariant.String),
            # 7
            QgsField("Settlement", QVariant.String),
            # 8
            QgsField("District", QVariant.String),
            # 9
            QgsField("ParcelLocation", QVariant.String),
            # 10
            QgsField("StreetType", QVariant.String),
            # 11
            QgsField("StreetName", QVariant.String),
            # 12
            QgsField("Building", QVariant.String),
            # 13
            QgsField("Block", QVariant.String),
            # 14
            QgsField("AdditionalInfo", QVariant.String),
            # 15 Категорія земель
            QgsField("Category", QVariant.String),
            # 16 Цільове призначення (використання) земельної ділянки
            QgsField("Purpose", QVariant.String),
            # 17 Цільове призначення (використання) згідно із документом
            QgsField("Use", QVariant.String),
            # 18 Код Форма власності на земельну ділянку
            QgsField("Code", QVariant.String),
        ]
        # endregion
        # region📌 Псевдоніми полів шару Ділянка
        aliases = {
            # 1
            "ParcelID": "Номер ділянки",
            # 2
            "Description": "Опис",
            # 3
            "AreaSize": "Площа",
            # 4
            "AreaUnit": "Одиниця виміру",
            # 5
            "DeterminationMethod": "Спосіб визначення площі",
            # 6
            "Region": "Регіон",
            # 7
            "Settlement": "Назва населеного пункту",
            # 8
            "District": "Назва району",
            # 9
            "ParcelLocation": "Відношення до населеного пункту",
            # 10
            "StreetType": "Тип (вулиця, проспект, провулок тощо)",
            # 11
            "StreetName": "Назва вулиці",
            # 12
            "Building": "Номер будинку",
            # 13
            "Block": "Номер корпусу",
            # 14
            "AdditionalInfo": "Додаткова інформація",
            # 15
            "Category": "Категорія земель",
            # 16
            "Purpose": "Цільове призначення (використання)",
            # 17
            "Use": "Цільове призначення згідно із документом",
            # 18
            "Code": "Код форми власності",
        }
        # endregion
        # region📌 Додаємо поля і псевдоніми до шару
        layer_provider.addAttributes(fields)
        layer.updateFields()

        if len(fields) == len(aliases):
            for field_name, alias in aliases.items():
                # log_msg(logFile, f"{layer.fields().indexOf(field_name)}. {field_name}, {alias}")
                layer.setFieldAlias(layer.fields().indexOf(field_name), alias)
        else:
            log_msg(logFile, "Кількість полів не відповідає кількості псевдонімів.")
        # endregion
        # region📌 Комбобокс для категорії земель
        index = layer.fields().indexOf("Category")
        if (index >= 0):
            setup = QgsEditorWidgetSetup("ValueMap", {
                "map": category_map,
                "UseMap": "true"
            })
            layer.setEditorWidgetSetup(index, setup)
        # endregion
        # region📌 Комбобокс для цільового призначення
        index = layer.fields().indexOf("Purpose")
        if (index >= 0):
            setup = QgsEditorWidgetSetup("ValueMap", {
                "map": purpose_map,
                "UseMap": "true"
            })
            layer.setEditorWidgetSetup(index, setup)
        # endregion
        # region📌 Комбобокс Коду форми власності
        index = layer.fields().indexOf("Code")
        if (index >= 0):
            setup = QgsEditorWidgetSetup("ValueMap", {
                "map": code_map,
                "UseMap": "true"
            })
            layer.setEditorWidgetSetup(index, setup)
        # endregion
        # region📌 Знаходимо значення полів
        parcel_id = metric_info.findtext("ParcelID", "")
        description = metric_info.findtext("Description", "")
        area_size = metric_info.findtext("Area/Size", "")
        area_unit = metric_info.findtext("Area/MeasurementUnit", "")
        # region Метод визначення площі:
        # area_method <--> <DeterminationMethod>
        # Метод визначення площі варіанти у xml:
        # 1)<ExhangeFileCoordinates></ExhangeFileCoordinates>, 2)<DocExch></DocExch>, 
        # 3)<Calculation>
        #   <CoordinateSystem>
        #       Варіанти:
        #       1. <SC42></SC42>, 
        #       2. <SC42_3></SC42_3>, 
        #       3. <Local>МСК ХХ</Local>,
        #       4. <USC2000></USC2000>,
        #       5. <WGS84></WGS84>,
        #       6. <SC63>
        #               <X></X>
        #               <C></C>
        #               <P></P>
        #               <T></T>
        #          </SC63>
        #   </CoordinateSystem>
        # </Calculation>
        # 
        def get_determination_method_label(self):
            from .common import area_determination_map  # Імпортуємо тут або на початку модуля

            det_elem = self.root.find(".//ParcelMetricInfo/Area/DeterminationMethod")
            if det_elem is None or not len(det_elem):
                return ""

            # Якщо є <ExchangeFileCoordinates/>
            if det_elem.find("ExchangeFileCoordinates") is not None:
                return area_determination_map.get("<ExhangeFileCoordinates/>", "За координатами обмінного файлу")

            # Якщо є <DocExch/>
            if det_elem.find("DocExch") is not None:
                return area_determination_map.get("<DocExch/>", "Згідно із правовстановлювальним документом")

            # Якщо є <Calculation>/<CoordinateSystem>
            calculation = det_elem.find("Calculation/CoordinateSystem")
            if calculation is not None:
                # Перевіряємо дочірні елементи
                if calculation.find("SC42") is not None:
                    return area_determination_map.get("<Calculation><CoordinateSystem><SC42/></CoordinateSystem></Calculation>", "Переобчислення з 'СК-42' (6 град зона)")
                if calculation.find("SC42_3") is not None:
                    return area_determination_map.get("<Calculation><CoordinateSystem><SC42_3/></CoordinateSystem></Calculation>", "Переобчислення з 'СК-42' (3 град зона)")
                if calculation.find("USC2000") is not None:
                    return area_determination_map.get("<Calculation><CoordinateSystem><USC2000/></CoordinateSystem></Calculation>", "Переобчислення з 'УСК2000'")
                if calculation.find("WGS84") is not None:
                    return area_determination_map.get("<Calculation><CoordinateSystem><WGS84/></CoordinateSystem></Calculation>", "Переобчислення з 'WGS84'")
                if calculation.find("Local") is not None:
                    msk_text = calculation.findtext("Local", "").strip()
                    return f"Переобчислення з місцевої системи координат '{msk_text}'"
                if calculation.find("SC63") is not None:
                    sc63 = calculation.find("SC63")
                    # Шукаємо активний тег всередині SC63
                    if sc63.find("X") is not None:
                        return area_determination_map.get("<Calculation><CoordinateSystem><SC63><X/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-X'")
                    if sc63.find("C") is not None:
                        return area_determination_map.get("<Calculation><CoordinateSystem><SC63><C/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-C'")
                    if sc63.find("P") is not None:
                        return area_determination_map.get("<Calculation><CoordinateSystem><SC63><P/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-P'")
                    if sc63.find("T") is not None:
                        return area_determination_map.get("<Calculation><CoordinateSystem><SC63><T/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-T'")

            return "Невідомо"
        area_method = get_determination_method_label(self)
        # log_msg(logFile, f"Метод визначення площі = {area_method}")
        # QMessageBox.information(None, "label", label)


        ns = ""
        # endregion area_method = ... (Метод визначення площі)
        # region Комбобокс для Методу визначення площі
        # Список варіантів для комбобокса
        determination_variants = [
            "За координатами обмінного файлу",
            "Згідно із правовстановлювальним документом",
            "Переобчислення з 'СК-42' (6 град зона)",
            "Переобчислення з 'СК-42' (3 град зона)",
            "Переобчислення з 'УСК2000'",
            "Переобчислення з 'WGS84'",
            "Переобчислення з 'SC63-X'",
            "Переобчислення з 'SC63-C'",
            "Переобчислення з 'SC63-P'",
            "Переобчислення з 'SC63-T'",
            # Окремий варіант
            "Переобчислення з місцевої системи координат"  
        ]
        # Створюємо ValueMap (назва → код)
        value_map = {v: v for v in determination_variants}

        index = layer.fields().indexOf("DeterminationMethod")
        if index != -1:
            setup = QgsEditorWidgetSetup("ValueMap", {"map": value_map, "UseMap": "true"})
            layer.setEditorWidgetSetup(index, setup)
        # endregion Комбобокс для Методу визначення площі 
        region = metric_info.findtext("../ParcelLocationInfo/Region", "")
        settlement = metric_info.findtext("../ParcelLocationInfo/Settlement", "")
        district = metric_info.findtext("../ParcelLocationInfo/District", "")
        # parcel_location: Відношення до населеного пункту
        # елемент ParcelLocationInfo/ParcelLocation може мати один з двох
        # дочірніх елементів: <Rural></Rural> або <Urban></Urban>
        # напиши код, який присвоїть parcel_location значення
        # "За межами населеного пункту" у першому випадку і
        # "У межах населеного пункту" у другому
        location_info = parcel_info.find("ParcelLocationInfo/ParcelLocation", ns)
        parcel_location = ""
        if location_info is not None:
            if location_info.find("Rural", ns) is not None:
                parcel_location = "За межами населеного пункту"
            elif location_info.find("Urban", ns) is not None:
                parcel_location = "У межах населеного пункту"
        street_type = location_info.findtext("../ParcelAddress/StreetType", "")
        street_name = location_info.findtext("../ParcelAddress/StreetName", "")
        building = location_info.findtext("../ParcelAddress/Building", "")
        block = location_info.findtext("../ParcelAddress/Block", "")
        additional_info = location_info.findtext("../AdditionalInfoBlock/AdditionalInfo", "")
        category = parcel_info.findtext("CategoryPurposeInfo/Category", "")
        purpose = parcel_info.findtext("CategoryPurposeInfo/Purpose", "")
        use = parcel_info.findtext("CategoryPurposeInfo/Use", "")
        code = parcel_info.findtext("OwnershipInfo/Code", "")




        # endregion        
        # region📌 Зовнішні межі
        externals_element = metric_info.find(".//Externals/Boundary/Lines")
        if externals_element is not None:
            external_coords = self.linesToCoordinates(externals_element)
        else:
            external_coords = []

        internals_element = metric_info.find(".//Internals/Boundary/Lines")
        internal_coords_list = []
        if internals_element is not None:
            internal_coords_list.append(self.linesToCoordinates(internals_element))

            # log_calls(logFile, "\n\t.//Internals/Boundary/Lines\n\t" + str(internals_element))
        polygon = self.coordToPolygon(external_coords)
        for internal_coords in internal_coords_list:
            polygon.addInteriorRing(internal_coords)
        # endregion
        # region📌 Ділянка -> Canvas
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry(polygon))
        feature.setAttributes([
            parcel_id,
            description,
            float(area_size) if area_size else None,
            area_unit,
            area_method,
            region,
            settlement,
            district,
            parcel_location,
            street_type,
            street_name,
            building,
            block,
            additional_info,
            category,
            purpose,
            use,
            code,
            ])
        
        layer_provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)
        # endregion
        # region📌 Ділянка -> наверх
        tree_layer = QgsLayerTreeLayer(layer)
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        self.group.addChildNode(tree_layer)
        self.added_layers.append(tree_layer)
        self.last_to_first(group)
        # endregion
    def on_editing_stopped(self):
        """Обробник сигналу editingStopped."""
        #✔️ 2025.05.19 функція може бути викликана з будь-якого шару
        # викликається при зміні як атрибутів, так і геометрії об'єкта
        # означає що редагування зупинено і зміни у дереві xml
        # треба зберегти у файл xml        
        log_calls(logFile, f"Зміни збережено у файлі {self.xmlFilePath}.")
        self.layer_modified = True
        self.tree.write(self.xmlFilePath, encoding="utf-8", xml_declaration=True)
        self.show_message("on_editing_stopped", f"Зміни збережено у файлі {self.xmlFilePath}.")


    def handle_parcel_attribute_change(self, layer, fid, field_index, new_value):

        field_name = layer.fields()[field_index].name()
        log_calls(logFile, f"Зміна значення поля №{field_name} на {new_value}")
    
        # блокувати треба щоб, не було повторного виклику форм вводу
        # при відміні користувачем зроблених змін 
        if self.block_attribute_handling:
            return 

        # Вихід (return), якщо self.id заморожений перед викликом != self.id 
        if layer.customProperty("xml_layer_id") != self.id:
            return

        # Випадок зміни "Спосіб визначення площі" - найскладніший
        if field_name == "DeterminationMethod":
            # 1.1: Переобчислення з місцевої системи координат
            log_msg(logFile, f"Зміна способу визначення площі на {new_value}")
            if new_value == "Переобчислення з місцевої системи координат":
                # треба ввести "Реєстраційний номер МСК
                msk_number, ok = QInputDialog.getText(
                    None,
                    "Реєстраційний номер МСК",
                    "Введіть номер місцевої системи координат (наприклад, 4610102):"
                )
                if ok and msk_number.strip():
                    # введено реєстраційний номер МСК -> формуємо новий текст комбобокса
                    new_label = f"Переобчислення з місцевої системи координат МСК {msk_number.strip()}"
                    # блокуємо отримання будь-яких сигналів
                    layer.blockSignals(True)
                    # TODO: не встановлюється новий текст комбобокса з + № МСК
                    # замість цього у якості костиля
                    self.show_message("Спосіб обчислення площі ділянки:", new_label)
                    layer.changeAttributeValue(fid, field_index, new_label)
                    # знову отримуємо сигнали
                    layer.blockSignals(False)
                    # Блокуємо настуні зміни всіх атрибутів даного id 
                    # для всіх атрибутів всіх шарів даної групи
                    #✔️ 2025.06.19 Gemini:
                    # імовірно, що блокування саме це блокує можливість
                    # подальшої зміни способу визначення площі ділянки
                    # на інший спосіб визначення площі ділянки
                    #self.block_attribute_handling = True 
                    # Оновлюємо tree
                    self.update_area_determination_in_tree(new_label)
                    # Оновлюємо форму
                    layer.triggerRepaint()
                else:
                    log_msg(logFile, "Номер МСК не введено — зміна скасована❗")
                return # "Спосіб визначення площі" -> МСК
            else:
                # Спосіб визначення площі ділянки не Переобчислення з МСК
                log_msg(logFile, f"Спосіб визначення площі ділянки змінено на {new_value}")
                # self.show_message("handle_parcel_attribute_change:", f"Спосіб визначення площі ділянки змінено на {new_value}")
                # Оновлюємо XML
                self.update_area_determination_in_tree(new_value)
            return # інші значення "Спосіб визначення площі"

        # тут починається обробка змін полів відмінних від "Спосіб визначення площі"

        if field_name == "ParcelID":
            log_msg(logFile, f"Зміна ParcelID на {new_value}")
            # Блокує QGIS
            # layer.changeAttributeValue(fid, field_index, new_value)
            element_path = "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/ParcelID"
            element = self.tree.find(element_path)
            if element is None:
                log_msg(logFile, f"Елемент за шляхом {element_path} не знайдено❗")
                return
            # Встановлюємо нове значення element
            element.text = new_value
            self.show_message("handle_parcel_attribute_change:", f"ParcelID змінено на {new_value}")
            
            
        
        return # інші поля
    def update_area_determination_in_tree(self, new_value):
        #✔️ 2025.06.09 
        # Проблема:
        # Після зміни способу визначення площі ділянки на 
        # "Переобчислення з місцевої системи координат"
        # повторна зміна на інший спосіб визначення площі
        # не оновлює XML файл (можливо, і дерево), а лише змінює текст у комбобоксі

        # Виклик цієї функції означає, що:
        # Змінено спосіб обчислення площі ділянки на переобчислення з МСК
        log_calls(logFile, f"{new_value}")
        # Шлях до елемента, який потрібно змінити відомий:
        element_path = "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/Area/DeterminationMethod"
        element = self.tree.find(element_path)
        if element is None:
            log_msg(logFile, f"Елемент за шляхом {element_path} не знайдено❗")
            return
        # Видаляємо всі дочірні елементи
        for child in list(element):
            element.remove(child)

        # Якщо нове значення починається з "Переобчислення з місцевої системи координат"
        if new_value.startswith("Переобчислення з місцевої системи координат"):
            # Знаходимо нове значення реєстраційного номера МСК
            number_MCK = new_value.split(" ")[-1]
            # Додаємо новий дочірній елемент
            new_element = ET.fromstring(f"<Calculation><CoordinateSystem><Local>{number_MCK}</Local></CoordinateSystem></Calculation>")
        # Нове значення інше ніж "Переобчислення з місцевої системи координат"
        else:
            # "За координатами обмінного файлу",
            # "Згідно із правовстановлювальним документом",
            # "Переобчислення з 'СК-42' (6 град зона)",
            # "Переобчислення з 'СК-42' (3 град зона)",
            # "Переобчислення з 'УСК2000'",
            # "Переобчислення з 'WGS84'",
            # "Переобчислення з 'SC63-X'",
            # "Переобчислення з 'SC63-C'",
            # "Переобчислення з 'SC63-P'",
            # "Переобчислення з 'SC63-T'",

            log_msg(logFile, f"new_value = {new_value}")

            if new_value.startswith("Переобчислення з 'SC63"):
                zona = new_value[-2]
                log_msg(logFile, f"zona = {zona}")
                new_element = ET.fromstring(f"<Calculation><CoordinateSystem><SC63><{zona}/></SC63></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'УСК2000'"):
                new_element = ET.fromstring("<Calculation><CoordinateSystem><USC2000/></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'WGS84'"):
                new_element = ET.fromstring("<Calculation><CoordinateSystem><WGS84/></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'СК-42' (6 град зона)"):
                new_element = ET.fromstring("<Calculation><CoordinateSystem><SC42/></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'СК-42' (3 град зона)"):
                new_element = ET.fromstring("<Calculation><CoordinateSystem><SC42_3/></CoordinateSystem></Calculation>")
            if new_value.startswith("За координатами обмінного файлу"):
                new_element = ET.fromstring("<ExhangeFileCoordinates></ExhangeFileCoordinates>")
            if new_value.startswith("Згідно із правовстановлювальним документом"):
                new_element = ET.fromstring("<DocExch></DocExch>")
            

        # Додаємо новий дочірній елемент з текстом нового значення
        element.append(new_element)
    def show_message(self, header, message):
        iface.messageBar().pushMessage(
            header,  # Заголовок
            message,  # Текст повідомлення
            level=Qgis.Success,  # Тип повідомлення (зелений фон)
            duration=0  # 0 секунд — повідомлення буде жити вічно, поки не закриють
        )
    def last_to_first(self, group):
        """Переміщує останній дочірній вузол групи шарів на першу позицію."""
        if group is None:
            return

        children = group.children()  # Отримуємо список дочірніх вузлів
        child_count = len(children)  # Отримуємо кількість дочірніх вузлів

        if child_count < 2:
            return

        last_child = children[-1]  # Отримуємо останній дочірній вузол
        cloned_last_child = last_child.clone() # Клонуємо останній дочірній вузол

        group.insertChildNode(0, cloned_last_child) # Вставляємо клон на першу позицію
        group.removeChildNode(last_child) # Видаляємо оригінальний останній дочірній вузол
    def get_full_name(self, person_element):

        # log_msg(logFile)

        if person_element is None:
            return ""  # Якщо елемент не знайдено, повертаємо порожній рядок

        # Отримуємо окремі частини і перевіряємо, чи вони існують
        last_name = person_element.find("LastName").text if person_element.find("LastName") is not None else ""
        first_name = person_element.find("FirstName").text if person_element.find("FirstName") is not None else ""
        middle_name = person_element.find("MiddleName").text if person_element.find("MiddleName") is not None else ""

        # Формуємо повне ім'я
        full_name = f"{last_name} {first_name} {middle_name}".strip()
        return full_name
    def add_quartal(self):

        # log_calls(logFile)

        quarter_info = {}
        quarter_number = self.root.find(".//CadastralQuarterInfo/CadastralQuarterNumber").text

        for quarter in self.root.findall(".//CadastralQuarterInfo"):
            local_authority = quarter.find("RegionalContacts/LocalAuthorityHead")
            dkzr_head = quarter.find("RegionalContacts/DKZRHead")

            quarter_info[quarter_number] = {
                "LocalAuthorityHead": {
                    "LastName": local_authority.find("LastName").text,
                    "FirstName": local_authority.find("FirstName").text,
                    "MiddleName": local_authority.find("MiddleName").text,
                },
                "DKZRHead": {
                    "LastName": dkzr_head.find("LastName").text,
                    "FirstName": dkzr_head.find("FirstName").text,
                    "MiddleName": dkzr_head.find("MiddleName").text,
                },
            }

        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, "Кадастровий квартал", "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/quarter.qml")
        layer_provider = layer.dataProvider()

        layer_provider.addAttributes([
            QgsField("CadastralQuarterNumber", QVariant.String),
            QgsField("LocalAuthorityHead", QVariant.String),
            QgsField("DKZRHead", QVariant.String)
        ])
        layer.updateFields()

        for quarter in self.root.findall(".//CadastralQuarterInfo"):
            externals_element = quarter.find(".//Externals/Boundary/Lines")
            # log_calls(logFile, "\n\t.//Externals/Boundary/Lines\n\t" + str(externals_element))
            if externals_element is not None:
                external_coords = self.linesToCoordinates(externals_element)

                logstr = ''
                i = 0
                for point in external_coords:
                    i += 1
                    logstr += f"\n\t {str(i)}. {point.x():.2f}, {point.y():.2f}"
                # log_calls(logFile, "\n\t external_coords: " + logstr)

            internals_element = quarter.find(".//Internals/Boundary/Lines")
            # log_calls(logFile, "\n\t.//Internals/Boundary/Lines\n\t" + str(externals_element))

            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.linesToCoordinates(internals_element))

            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)




        for quarter in self.root.findall(".//CadastralQuarterInfo"):
            auth_head = quarter.find("RegionalContacts/LocalAuthorityHead")
            dkzr_head = quarter.find("RegionalContacts/DKZRHead")

            auth_head_full_name = self.get_full_name(auth_head)
            dkzr_head_full_name = self.get_full_name(dkzr_head)

            # log_calls(logFile, f"Auth Head: {auth_head_full_name}")
            # log_calls(logFile, f"DKZR Head: {dkzr_head_full_name}")

        features = []
        feature = QgsFeature(layer.fields())

        feature.setGeometry(QgsGeometry(polygon))
        feature.setAttribute("CadastralQuarterNumber", quarter_number)
        feature.setAttribute("LocalAuthorityHead", auth_head_full_name)
        feature.setAttribute("DKZRHead", dkzr_head_full_name)

        # Додаємо об'єкт до списку
        features.append(feature)

        # Оновити шар
        layer.triggerRepaint()

        layer_provider.addFeatures(features)

        # Додаємо шар до проекту, але не до дерева шарів
        QgsProject.instance().addMapLayer(layer, False) 
        tree_layer = QgsLayerTreeLayer(layer)
        # Get the group directly or create it if it doesn't exist:
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        self.added_layers.append(tree_layer)
        self.last_to_first(group)
    def last_to_first(self, group):
        """Переміщує останній дочірній вузол групи шарів на першу позицію."""
        if group is None:
            return

        children = group.children()  # Отримуємо список дочірніх вузлів
        child_count = len(children)  # Отримуємо кількість дочірніх вузлів

        if child_count < 2:
            return

        last_child = children[-1]  # Отримуємо останній дочірній вузол
        cloned_last_child = last_child.clone() # Клонуємо останній дочірній вузол

        group.insertChildNode(0, cloned_last_child) # Вставляємо клон на першу позицію
        group.removeChildNode(last_child) # Видаляємо оригінальний останній дочірній вузол
    def removeLayer(self, layer_name, group_name=None):
        """
            Removes a layer with the given name from a specified group 
            or from the root of the layer tree.
            
            Args:
                layer_name (str): 
                    The name of the layer to be removed.
                group_name (str, optional): 
                    The name of the group from which to remove the layer. 
                    If None or "", the layer is searched for in the root 
                    of the layer tree. Defaults to None.

        """
        # log_calls(logFile, f"'{layer_name}'")

        root = QgsProject.instance().layerTreeRoot()

        if group_name is None or group_name == "":
            parent = root
        else:
            parent = root.findGroup(group_name)
            if parent is None:
                log_calls(logFile, f"'{group_name}' не знайдена. \nШар '{layer_name}' не видалено.")
                return

        # Знаходимо шар у батьківському вузлі (групі або корені) за іменем
        for child in parent.children():
            if isinstance(child, QgsLayerTreeLayer) and child.name() == layer_name:
                layer_id = child.layerId()  # Отримуємо ID шару карти
                QgsProject.instance().removeMapLayer(layer_id)  # Видаляємо шар з проекту
                parent.removeChildNode(child)  # Видаляємо шар з дерева
                log_calls(logFile, f"Шар '{layer_name}' видалено з групи {group_name}") 
                return  # Виходимо з функції після видалення шару

        # log_calls(logFile, f"Шар '{layer_name}' не знайдено в групі {group_name}")
    def add_lines(self):

        # log_calls(logFile)

        layer_name = "Лінії XML"
        # log_msg(logFile, " layer_name = " + layer_name)
        self.removeLayer(layer_name)
        layer = QgsVectorLayer("LineString?crs=" + self.crsEpsg, layer_name, "memory")

        if layer.isValid():
            layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/lines.qml")
            # додаємо шар до проекту, але не до дерева шарів
            QgsProject.instance().addMapLayer(layer, False)
            tree_layer = QgsLayerTreeLayer(layer)
            
            # Додаємо шар до групи
            self.group.addChildNode(tree_layer) 
            # log_msg(logFile, f"Додано шар {layer.name()}")
            # Стара модель підключення обробника сигналів для шару
            # Підключаємо обробник сигналів для шару
            #if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
            # Оновлюємо список шарів 
            self.added_layers.append(tree_layer)
            # Переміщуємо шар на верх групи
            # self.last_to_first(group) 

        else:
            QMessageBox.critical(self, "xml_ua", "Виникла помилка при створенні шару ліній.")

        provider = layer.dataProvider()
        provider.addAttributes([QgsField("ULID", QVariant.String)])
        provider.addAttributes([QgsField("Length", QVariant.String)])
        layer.updateFields()

        self.qgisLinesXML = {}
        for point in self.root.findall(".//Point"):
            uidp = point.find("UIDP").text
            x = float(point.find("X").text)
            y = float(point.find("Y").text)
            self.qgisLinesXML[uidp] = QgsPointXY(y, x)
            # log_msg(logFile, " self.qgisLinesXML[" + uidp + "] = " + str(self.qgisLinesXML[uidp]))

        # Додаємо полілінії на шар
        for pl in self.root.findall(".//PL"):
            point_ids = [p.text for p in pl.find("Points").findall("P")]
            line_ULID = pl.find("ULID")
            line_length = pl.find("Length")
            # log_msg(logFile, " line_ULID = " + line_ULID.text)
            polyline_points = [self.qgisLinesXML[pid] for pid in point_ids if pid in self.qgisLinesXML]
            fields = layer.fields()
            feature = QgsFeature(fields)
            feature["ULID"] = line_ULID.text
            feature["Length"] = line_length.text
            # log_msg(logFile, " feature['ULID'] = " + feature["ULID"])
            feature.setGeometry(QgsGeometry.fromPolylineXY(polyline_points))
            provider.addFeatures([feature])
        
            
        layer.updateExtents()
        layer.triggerRepaint(deferredUpdate = True)

        return
    def add_lands(self):
        """
        Імпортує угіддя з XML-файлу та додає їх як новий шар до проекту QGIS.
        Враховує, що угідь може бути декілька.
        """
        # log_msg(logFile)

        layer_name = "Угіддя"
        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, layer_name, "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/lands_parcel.qml")
        layer_provider = layer.dataProvider()
        fields = [
            QgsField("CadastralCode", QVariant.String),
            QgsField("LandCode", QVariant.String),
            QgsField("Size", QVariant.Double),
        ]
        layer_provider.addAttributes(fields)
        layer.updateFields()

        for lands_parcel in self.root.findall(".//LandsParcel/LandParcelInfo/MetricInfo"):
            cadastral_code = lands_parcel.find("../CadastralCode").text if lands_parcel.find("../CadastralCode") is not None else None
            land_code = lands_parcel.find("../LandCode").text if lands_parcel.find("../LandCode") is not None else None
            size_element = lands_parcel.find("./Area/Size")
            size = float(size_element.text) if size_element is not None and size_element.text else None

            # Зовнішні межі
            externals_element = lands_parcel.find(".//Externals/Boundary/Lines")
            if externals_element is not None:
                external_coords = self.linesToCoordinates(externals_element)
            else:
                external_coords = []

            # Внутрішні межі
            internals_element = lands_parcel.find(".//Internals/Boundary/Lines")
            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.linesToCoordinates(internals_element))

            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)

            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([cadastral_code, land_code, size])
            layer_provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)  # Додаємо шар до проекту, але не до дерева шарів
        tree_layer = QgsLayerTreeLayer(layer)
        # Get the group directly or create it if it doesn't exist:
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        #log_msg(logFile, f"Додано шар {layer.name()}")
        # Стара модель підключення обробника сигналів для шару
        # Підключаємо обробник сигналів для шару
        #if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
        self.last_to_first(group) 
    def add_leases(self):
        """
        Імпортує дані про оренду з XML-файлу та додає їх як новий шар до проекту QGIS.
        """
        # log_calls(logFile)

        layer_name = "Оренда"
        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, layer_name, "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/lease.qml")
        layer_provider = layer.dataProvider()
        fields = [
            QgsField("LeaseDuration", QVariant.String),
            QgsField("RegistrationDate", QVariant.String),
            QgsField("Area", QVariant.Double),
        ]
        layer_provider.addAttributes(fields)
        layer.updateFields()

        leases_parent = self.root.find(".//Leases")
        if leases_parent is None:
            log_msg(logFile, "Розділ Leases відсутній. Оренди не імпортовано.")
            return

        for lease in leases_parent.findall(".//LeaseInfo"):
            lease_duration = lease.find(".//LeaseAgreement/LeaseTerm/LeaseDuration").text if lease.find(".//LeaseAgreement/LeaseTerm/LeaseDuration") is not None else None
            registration_date = lease.find(".//LeaseAgreement/RegistrationDate").text if lease.find(".//LeaseAgreement/RegistrationDate") is not None else None
            area_element = lease.find(".//LeaseAgreement/Area")
            area = float(area_element.text) if area_element is not None and area_element.text else None

            # Отримуємо зовнішні межі з об'єкта (оренди)
            externals_element = lease.find(".//Externals/Boundary/Lines")
            if externals_element is not None:
                external_coords = self.lines_element2polygone(externals_element)
            else:
                external_coords = []

            # Внутрішні межі
            internals_element = lease.find(".//Internals/Boundary/Lines")
            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.lines_element2polygone(internals_element))

            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)

            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([lease_duration, registration_date, area])
            layer_provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)  # Додаємо шар до проекту, але не до дерева шарів
        tree_layer = QgsLayerTreeLayer(layer)
        # Get the group directly or create it if it doesn't exist:
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        # log_msg(logFile, f"Додано шар {layer.name()}")
        # Стара модель підключення обробника сигналів для шару
        # Підключаємо обробник сигналів для шару
        #if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
        self.last_to_first(group) 
    def add_subleases(self):
        """
        Імпортує дані про суборенду з XML-файлу та додає їх як новий шар до проекту QGIS.
        """
        # log_calls(logFile)

        layer_name = "Суборенда"
        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, layer_name, "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/sublease.qml")
        layer_provider = layer.dataProvider()
        fields = [
            QgsField("RegistrationDate", QVariant.String),
            QgsField("Area", QVariant.Double),
        ]
        layer_provider.addAttributes(fields)
        layer.updateFields()

        subleases_parent = self.root.find(".//Subleases")
        if subleases_parent is None:
            log_msg(logFile, "Розділ Subleases відсутній. Суборенди не імпортовано.")
            return

        for sublease in subleases_parent.findall(".//SubleaseInfo"):
            registration_date = sublease.find(".//RegistrationDate").text if sublease.find(".//RegistrationDate") is not None else None
            area_element = sublease.find(".//Area")
            area = float(area_element.text) if area_element is not None and area_element.text else None

            # Отримуємо зовнішні межі з об'єкта (суборенди)
            externals_element = sublease.find(".//Externals/Boundary/Lines")
            if externals_element is not None:
                external_coords = self.lines_element2polygone(externals_element)
            else:
                external_coords = []

            # Внутрішні межі
            internals_element = sublease.find(".//Internals/Boundary/Lines")
            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.lines_element2polygone(internals_element))

            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)

            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([registration_date, area])
            layer_provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False)  # Додаємо шар до проекту, але не до дерева шарів
        tree_layer = QgsLayerTreeLayer(layer)
        # Get the group directly or create it if it doesn't exist:
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        # log_msg(logFile, f"Додано шар {layer.name()}")
        # Стара модель підключення обробника сигналів для шару
        # Підключаємо обробник сигналів для шару
        #if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
        self.last_to_first(group) 
    def add_restrictions(self):
        """
        Імпортує дані про обмеження з XML-файлу та додає їх як новий шар до проекту QGIS.
        """
        # log_calls(logFile)

        layer_name = "Обмеження"
        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, layer_name, "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/restriction.qml")
        layer_provider = layer.dataProvider()
        fields = [
            QgsField("RestrictionCode", QVariant.String),
            QgsField("RestrictionName", QVariant.String),
            QgsField("StartDate", QVariant.String),
            QgsField("ExpirationDate", QVariant.String),
        ]
        layer_provider.addAttributes(fields)
        layer.updateFields()

        restrictions_parent = self.root.find(".//Restrictions")
        if restrictions_parent is None:
            log_msg(logFile, "Розділ Restrictions відсутній. Обмеження не імпортовано.")
            return

        for restriction in restrictions_parent.findall(".//RestrictionInfo"):
            restriction_code = restriction.find(".//RestrictionCode").text if restriction.find(".//RestrictionCode") is not None else None
            restriction_name = restriction.find(".//RestrictionName").text if restriction.find(".//RestrictionName") is not None else None
            start_date = restriction.find(".//RestrictionTerm/Time/StartDate").text if restriction.find(".//RestrictionTerm/Time/StartDate") is not None else None
            expiration_date = restriction.find(".//RestrictionTerm/Time/ExpirationDate").text if restriction.find(".//RestrictionTerm/Time/ExpirationDate") is not None else None

            # Отримуємо зовнішні межі з об'єкта (обмеження)
            externals_element = restriction.find(".//Externals/Boundary/Lines")
            if externals_element is not None:
                external_coords = self.lines_element2polygone(externals_element)
            else:
                external_coords = []

            # Внутрішні межі
            internals_element = restriction.find(".//Internals/Boundary/Lines")
            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.lines_element2polygone(internals_element))

            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)

            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([restriction_code, restriction_name, start_date, expiration_date])
            layer_provider.addFeature(feature)

        # Додаємо шар до проекту, але не до дерева шарів
        QgsProject.instance().addMapLayer(layer, False)  
        tree_layer = QgsLayerTreeLayer(layer)
        # Get the group directly or create it if it doesn't exist:
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        # log_msg(logFile, f"Додано шар {layer.name()}")
        # Стара модель підключення обробника сигналів для шару
        # Підключаємо обробник сигналів для шару
        #if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
        self.last_to_first(group) 
    def lines_element2polygone(self, lines_element):
        # Останній варіант
        """ Формує список координат замкненого полігону на основі ULID ліній
            і їх точок.

            Parameters:
                lines_element (xml.etree.ElementTree.Element):
                Елемент, який містить піделементи <Line>.

            Returns:
                list: Список координат замкненого полігону.
        """

        # log_calls(logFile, f"lines_element = {lines_element.tag}")

        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        # Зчитати всі ULID ліній
        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//Line"):
            i += 1
            ulid = line.find("ULID").text
            # logstr += '\n\t' + ulid + '. '+ str(line)
            logstr += '\n\t' + ulid + '. '

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
            elif ulid:
                raise ValueError(f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError("Лінія не містить атрибуту унікального ідентифікатора.")
        # log_calls(logFile, "\n\t   ULID:" + logstr)

        # i = 0
        # for line in lines:
        #     log_msg(logFile, f"lines[{i}][0] = {lines[i][0]}")
        #     log_msg(logFile, f"lines[{i}][1] = {lines[i][1]}")
        #     i += 1



        # Формуємо замкнений полігон
        if not lines:
            return []

        polygon_coordinates = []
        used_lines = set()
        current_line = lines[0]
        polygon_coordinates.extend(current_line[1])  # Додати точки першої лінії
        used_lines.add(current_line[0])

        while len(used_lines) < len(lines):
            # Пошук наступної лінії, що з'єднується
            for ulid, coords in lines:
                if ulid in used_lines:
                    continue
                if coords[0] == polygon_coordinates[-1]:  # З'єднання кінця попередньої лінії з початком наступної
                    polygon_coordinates.extend(coords[1:])
                    used_lines.add(ulid)
                    break
                elif coords[-1] == polygon_coordinates[-1]:  # З'єднання кінця попередньої лінії з кінцем наступної
                    polygon_coordinates.extend(reversed(coords[:-1]))
                    used_lines.add(ulid)
                    break
            else:
                raise ValueError("Неможливо сформувати замкнений полігон — деякі лінії не з'єднуються.")

        # Замикання полігону
        if polygon_coordinates[0] != polygon_coordinates[-1]:
            polygon_coordinates.append(polygon_coordinates[0])

        return polygon_coordinates
    def lines_element2polyline(self, lines_element):
        """

        Parameters:
            lines_element (xml.etree.ElementTree.Element):
                Елемент, який містить піделементи <Line>.
            self.qgisLines (dict): Словник, де
                ключ — ULID (унікальний ідентифікатор),
                а значення — список координат [QgsPointXY, QgsPointXY].

        Returns:
            list: Список координат полілінії.
        """
        # Формує список координат полілінії 
        # на основі ULID ліній та їх точок.
        # На відміну від lines_element2polygone, 
        # не перевіряє полілінію на замкнутість.
        # Полілінія може бути як замкнутою, так і незамкнутою.
        #✔️ 2025.03.27 13:32
        # Викликається з add_adjacents
        # має специфічні особливості, характерні
        # для використання в обробці інформації про суміжників

        # log_calls(logFile)

        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        # Зчитати всі ULID ліній
        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//Line"):
            i += 1
            ulid = line.find("ULID").text

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
                coords_str = ", ".join([f"{point.x():.2f}, {point.y():.2f}" for point in self.qgisLines[ulid]])
                logstr += f"{i}. {ulid}: {coords_str}\n"
            elif ulid:
                raise ValueError(f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError("Лінія не містить атрибуту унікального ідентифікатора.")
        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        # Зчитати всі ULID ліній
        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//Line"):
            i += 1
            ulid = line.find("ULID").text

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
                coords_str = ", ".join([f"{point.x():.2f}, {point.y():.2f}" for point in self.qgisLines[ulid]])
                logstr += f"{i}. {ulid}: {coords_str}\n"
            elif ulid:
                raise ValueError(f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError("Лінія не містить атрибуту унікального ідентифікатора.")
        # log_msg(logFile, "\nlines: \n" + logstr)

        # Створюємо пустий список координат polyline
        polyline = []

        if not lines:
            # raise ValueError("Нема суміжників.")
            QMessageBox.critical(self, "xml_ua", "Нема суміжників.")
            return None

        # Якщо в lines 1 елемент і polyline пустий - анклав - вертаємо lines_element2polygone(lines_element)
        if len(lines) == 1:
            return self.lines_element2polygone(lines_element)

        # Глибокі копії lines[0][1], ..., lines[0][-1] додаються в кінець polyline у прямому порядку
        polyline.extend([QgsPointXY(point.x(), point.y()) for point in lines[0][1]])

        # Видаляємо lines[0]
        lines.pop(0)

        # Якщо lines пустий - завершення
        if not lines:
            return polyline

        while lines:
            found_next_line = False

            # Шукаємо співпадіння polyline[-1] (кінець) з початками залишку lines[0][1],...lines[-1][1]
            for i, (ulid, coords) in enumerate(lines):
                if coords[0] == polyline[-1]:
                    # Додаємо точки, крім першої (щоб уникнути дублювання)
                    polyline.extend([QgsPointXY(point.x(), point.y()) for point in coords[1:]])
                    lines.pop(i)
                    found_next_line = True
                    break

            if found_next_line:
                continue

            # Шукаємо співпадіння polyline[-1] (кінець) з кінцями залишку lines[0][-1],...lines[-1][-1]
            for i, (ulid, coords) in enumerate(lines):
                if coords[-1] == polyline[-1]:
                    # Додаємо точки в зворотньому порядку, крім останньої
                    polyline.extend([QgsPointXY(point.x(), point.y()) for point in reversed(coords[:-1])])
                    lines.pop(i)
                    found_next_line = True
                    break

            if found_next_line:
                continue

            # Шукаємо співпадіння polyline[0] (початок) з кінцями залишку lines[0][-1],...lines[-1][-1]
            for i, (ulid, coords) in enumerate(lines):
                if coords[-1] == polyline[0]:
                    # Додаємо точки в зворотньому порядку, крім останньої
                    polyline = [QgsPointXY(point.x(), point.y()) for point in reversed(coords[:-1])] + polyline
                    lines.pop(i)
                    found_next_line = True
                    break

            if found_next_line:
                continue

            # Шукаємо співпадіння polyline[0] (початок) з початками залишку lines[0][1],...lines[-1][1]
            for i, (ulid, coords) in enumerate(lines):
                if coords[0] == polyline[0]:
                    # Додаємо точки, крім першої (щоб уникнути дублювання)
                    polyline = [QgsPointXY(point.x(), point.y()) for point in coords[1:]] + polyline
                    lines.pop(i)
                    found_next_line = True
                    break

            if not found_next_line:
                raise ValueError("Полілінія не з'єднана.")

        log_str = ""
        log_str_coords = ""
        i = 0
        for coordinate in polyline:
            i += 1
            log_str += f"{i}. {coordinate.x():.2f}, {coordinate.y():.2f}\n"
            log_str_coords += f"{i}. {coordinate} \n"
        # log_msg(logFile, "polyline_coordinates (x, y): \n" + log_str)

        return polyline
    def add_adjacents(self):
        """
        Імпортує дані про суміжників з XML-файлу та додає їх як новий шар до проекту QGIS.
        Враховує як замкнуті (анклави), так і незамкнуті полілінії суміжників.
        """
        # log_msg(logFile)

        layer_name = "Суміжник"
        # Видаляємо шар, якщо він вже існує
        self.removeLayer(layer_name)
        layer = QgsVectorLayer("LineString?crs=" + self.crsEpsg, layer_name, "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/adjacent.qml")
        layer_provider = layer.dataProvider()
        fields = [
            QgsField("CadastralNumber", QVariant.String),
            QgsField("Proprietor", QVariant.String),
        ]
        layer_provider.addAttributes(fields)
        layer.updateFields()

        # знаходимо елемент Суміжників у дереві
        adjacents = self.root.find(".//AdjacentUnits")
        if adjacents is None:
            log_msg(logFile, "Розділ AdjacentUnits відсутній. Суміжники не імпортовано.")
            return

        for adjacent in adjacents.findall(".//AdjacentUnitInfo"):

            # Знаходимо значення параметрів суміжника
            # Отримуємо кадастровий номер
            cadastral_number = adjacent.find(".//CadastralNumber").text if adjacent.find(".//CadastralNumber") is not None else None

            # Визначаємо власника
            proprietor = ""
            natural_person = adjacent.find(".//Proprietor/NaturalPerson/FullName")
            legal_entity = adjacent.find(".//Proprietor/LegalEntity")

            if natural_person is not None:
                last_name = natural_person.find("LastName").text if natural_person.find("LastName") is not None else ""
                first_name = natural_person.find("FirstName").text if natural_person.find("FirstName") is not None else ""
                middle_name = natural_person.find("MiddleName").text if natural_person.find("MiddleName") is not None else ""
                proprietor = f"{last_name} {first_name} {middle_name}".strip()
            elif legal_entity is not None:
                proprietor = legal_entity.find("Name").text if legal_entity.find("Name") is not None else ""

            # Отримуємо межі суміжника
            boundary_element = adjacent.find(".//AdjacentBoundary/Lines")
            if boundary_element is not None:

                # Отримуємо координати полілінії
                try:
                    boundary_coords = self.lines_element2polyline(boundary_element)
                except ValueError as e:
                    log_msg(logFile, f"Помилка при обробці суміжника {cadastral_number}: {e}")
                    continue

                logstr = ''
                i = 0
                for point in boundary_coords:
                    i += 1
                    logstr += f"\n\t {str(i)}. {point.x():.2f}, {point.y():.2f}"
                # log_msg(logFile, f"\n{proprietor}: " + logstr + "\n")

                if len(boundary_coords) >= 2:
                    # Створюємо QgsLineString з QgsPointXY
                    # line_string = QgsLineString([QgsPointXY(point.x(), point.y()) for point in boundary_coords])
                    line_string = QgsLineString([QgsPointXY(point.y(), point.x()) for point in boundary_coords])
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry(line_string))
                    feature.setAttributes([cadastral_number, proprietor])
                    layer_provider.addFeature(feature)
                elif len(boundary_coords) == 1:
                    log_msg(logFile, f"Суміжника {cadastral_number} неможливо відобразити, оскільки він складається з однієї точки")
                else:
                    log_msg(logFile, f"Суміжника {cadastral_number} неможливо відобразити, оскільки відсутні межі")

            else:
                log_msg(logFile, f"Для суміжника {cadastral_number} відсутній елемент AdjacentBoundary/Lines")

        QgsProject.instance().addMapLayer(layer, False)  # Додаємо шар до проекту, але не до дерева шарів
        tree_layer = QgsLayerTreeLayer(layer)
        # Get the group directly or create it if it doesn't exist:
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        # log_msg(logFile, f"Додано шар {layer.name()}")
        # Стара модель підключення обробника сигналів для шару
        # Підключаємо обробник сигналів для шару
        #if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
        self.last_to_first(group)

        layer.updateExtents()
        layer.triggerRepaint()
    def display_test_line(self):
        """
        Відображає тестову лінію на полотні QGIS.
        """
        log_calls(logFile)

        layer_name = "Тестова лінія"
        self.removeLayer(layer_name)

        layer = QgsVectorLayer("LineString?crs=" + self.crsEpsg, layer_name, "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/lines.qml")
        layer_provider = layer.dataProvider()

        # Точки для тестової лінії
        points = [
            QgsPointXY(5428619.05, 1260119.11),
            QgsPointXY(5428738.27, 1260179.85),
            QgsPointXY(5428888.77, 1260251.91),
            QgsPointXY(5428926.86, 1260196.32),
            QgsPointXY(5428934.09, 1260193.32),
        ]

        # Створюємо QgsLineString
        line_string = QgsLineString(points)

        # Створюємо QgsFeature
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry(line_string))

        # Додаємо QgsFeature до шару
        layer_provider.addFeature(feature)

        # Додаємо шар до проекту
        QgsProject.instance().addMapLayer(layer, False)
        tree_layer = QgsLayerTreeLayer(layer)
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        log_msg(logFile, f"Додано шар {layer.name()}")
        # Стара модель підключення обробника сигналів для шару
        # Підключаємо обробник сигналів для шару
        #if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
        self.last_to_first(group) 

        # Оновлюємо екстенти та перемальовуємо шар
        layer.updateExtents()
        layer.triggerRepaint()
