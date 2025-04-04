# -*- coding: utf-8 -*-

import os

from qgis.core import QgsLayerTreeGroup


from qgis.core import QgsLineString
from qgis.core import QgsGeometry
from qgis.core import QgsPolygon
from qgis.core import QgsProject
from qgis.core import QgsMultiPolygon
from qgis.core import QgsLayerTreeLayer
from qgis.core import QgsVectorLayer
from qgis.core import QgsField
from qgis.core import QgsFeature
from qgis.core import QgsPointXY


from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from lxml import etree
from xml.etree import ElementTree as ET

from .common import logFile
from .common import log_msg
from .common import log_calls

class xmlUaLayers:

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
        
        self.plugin = plugin  

        xmlUaLayers._id_counter += 1

        # унікальний ідентифікатор екземпляра класу
        self.id = xmlUaLayers._id_counter

        log_calls(logFile, f"id = {str(self.id)}")

        # ініціюємо список назв шарів QGIS
        self.layers = QgsProject.instance().mapLayers().values()

        # отримання кореня дерева шарів
        self.layers_root = QgsProject.instance().layerTreeRoot()
        
        self.xmlFilePath: str = xmlFilePath
        self.fileNameNoExt: str = os.path.splitext(os.path.basename(xmlFilePath))[0]

        # генеруємо унікальне ім'я групи шарів, в яку будуть поміщені шари xml  
        self.group_name = self.generate_group_name(self.fileNameNoExt)

        if tree is None:
            self.tree = ET.parse(self.xmlFilePath)
        else:
            self.tree = tree
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


    def create_group(self):

        # log_calls(logFile)
        #self.group = self.layers_root.findGroup(self.group_name)
        self.group = self.layers_root.addGroup(self.group_name)
        cloned_group = self.group.clone()
        self.layers_root.removeChildNode(self.group)
        self.layers_root.insertChildNode(0, cloned_group)
        self.group = cloned_group
        # log_calls(logFile, f"{self.group_name} створено і переміщено на початок дерева ш.")

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

        log_calls(logFile)

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
        if group:  # Check if the group exists
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
            
            group.addLayer(layer) # Add directly to the group only once
            self.added_layers.append(layer)

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
        group.addLayer(layer)  # Use addLayer directly on the group

        self.last_to_first(group)

        self.added_layers.append(layer)
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

        # log_msg(logFile)

        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, "Ділянка", "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/parcel.qml")
        layer_provider = layer.dataProvider()
        fields = [
            QgsField("ParcelID", QVariant.String),
            QgsField("Area", QVariant.Double),
            QgsField("Owners", QVariant.String),
        ]
        layer_provider.addAttributes(fields)
        layer.updateFields()

        parcel_id = self.root.find(".//Parcels/ParcelInfo/ParcelMetricInfo/ParcelID").text
        # log_calls(logFile, "\n\tparcel_id = " + parcel_id)

        for parcel in self.root.findall(".//Parcels/ParcelInfo/ParcelMetricInfo"):

            # Зовнішні межі
            externals_element = parcel.find(".//Externals/Boundary/Lines")
            # log_calls(logFile, "\n\t.//Externals/Boundary/Lines\n\t" + str(externals_element))
            if externals_element is not None:
                external_coords = self.linesToCoordinates(externals_element)

                logstr = ''
                i = 0
                for point in external_coords:
                    i += 1
                    logstr += f"\n\t {str(i)}. {point.x():.2f}, {point.y():.2f}"
                # log_calls(logFile, "\n\t external_coords: " + logstr)

            internals_element = parcel.find(".//Internals/Boundary/Lines")
            # log_calls(logFile, "\n\t.//Internals/Boundary/Lines\n\t" + str(externals_element))
            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.linesToCoordinates(internals_element))

            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)

            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([parcel_id])
            layer_provider.addFeature(feature)

        QgsProject.instance().addMapLayer(layer, False) # Додаємо шар до проекту, але не до дерева шарів
        tree_layer = QgsLayerTreeLayer(layer)
        # Get the group directly or create it if it doesn't exist:
        group = self.layers_root.findGroup(self.group_name)
        if group is None:
            group = self.layers_root.addGroup(self.group_name)

        # Додаємо шар до групи
        self.group.addChildNode(tree_layer) 
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
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
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
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
            log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
            # Підключаємо обробник сигналів для шару
            if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
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
                external_coords = self.lines_element2polygone(externals_element)
            else:
                external_coords = []

            # Внутрішні межі
            internals_element = lands_parcel.find(".//Internals/Boundary/Lines")
            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.lines_element2polygone(internals_element))

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
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
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
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
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
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
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
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
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

        # Перевірка наявності хоча б однієї лінії
        current_line_ulid = lines[0][0]  # Отримуємо ULID першої лінії
        current_line_coords = lines[0][1]  # Отримуємо координати першої лінії

        # Додати точки першої лінії
        polygon_coordinates.extend(current_line_coords)
        used_lines.add(current_line_ulid)

        while len(used_lines) < len(lines):
            found_next_line = False
            # Пошук наступної лінії, що з'єднується
            for ulid, coords in lines:
                if ulid in used_lines:
                    continue
                # Перевірка наявності точок в polygon_coordinates
                if not polygon_coordinates:
                    raise ValueError("polygon_coordinates is empty")
                # З'єднання кінця попередньої лінії з початком наступної
                if coords[0] == polygon_coordinates[-1]:
                    polygon_coordinates.extend(coords[1:])
                    used_lines.add(ulid)
                    current_line_ulid = ulid
                    found_next_line = True
                    break
                # З'єднання кінця попередньої лінії з кінцем наступної
                elif coords[-1] == polygon_coordinates[-1]:
                    polygon_coordinates.extend(reversed(coords[:-1]))
                    used_lines.add(ulid)
                    current_line_ulid = ulid
                    found_next_line = True
                    break
            if not found_next_line:
                # Якщо не знайдено наступної лінії, перевіряємо, чи можна замкнути полігон
                if polygon_coordinates[0] == polygon_coordinates[-1]:
                    return polygon_coordinates
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

        log_calls(logFile)

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
        log_msg(logFile, "polyline_coordinates (x, y): \n" + log_str)

        return polyline


    def add_adjacents(self):
        """
        Імпортує дані про суміжників з XML-файлу та додає їх як новий шар до проекту QGIS.
        Враховує як замкнуті (анклави), так і незамкнуті полілінії суміжників.
        """
        log_calls(logFile)

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
                log_msg(logFile, f"\n{proprietor}: " + logstr)

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
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
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
        log_msg(logFile, f"Додано шар {layer.name()} до групи {self.group.name()}")
        # Підключаємо обробник сигналів для шару
        if self.plugin: self.plugin.connect_layer_signals_for_layer(layer)
        # Оновлюємо список шарів 
        self.added_layers.append(tree_layer)
        # Переміщуємо шар на верх групи
        self.last_to_first(group) 

        # Оновлюємо екстенти та перемальовуємо шар
        layer.updateExtents()
        layer.triggerRepaint()











