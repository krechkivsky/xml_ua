# -*- coding: utf-8 -*-
import os, sys, inspect, configparser

from qgis.core import QgsProject,QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsLineString, QgsPolygon, QgsField, QgsMultiPolygon, QgsLayerTreeLayer
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from lxml import etree
from xml.etree import ElementTree as ET

from . import common

def XY(point):
    # logging(common.logFile)
    formatted_point = f"({point.x():.2f}, {point.y():.2f})"
    return formatted_point


class xmlUaLayers:
    ''' 
        Екземпляр класу створюється при відкритті xml файлу.
        При відкритті файлу використовується функціонал імпорту з xml.
        При створенні нового або збереженні змін треба розробити функціонал експорту в xml.
    '''
    _id_counter = 0
    
    def __init__(self, xmlFilePath = ""):
        
        xmlUaLayers._id_counter += 1
        self.id = xmlUaLayers._id_counter
        
        logging(common.logFile, f"xmlUaLayers._id_counter = {str(self.id)}")
        
        self.xmlFilePath: str = xmlFilePath
        self.fileNameNoExt: str = os.path.splitext(os.path.basename(xmlFilePath))[0]
        self.group_name = self.fileNameNoExt
        self.tree = ET.parse(self.xmlFilePath)
        self.root = self.tree.getroot()
        self.project = QgsProject.instance()
        self.crs = self.project.crs()
        self.crsEpsg = self.crs.authid()
        self.layers = QgsProject.instance().mapLayers().values()
        self.layers_root = QgsProject.instance().layerTreeRoot()
        self.group = self.layers_root.findGroup(self.group_name)
        self.dataINI = configparser.ConfigParser()
        self.dataINI.read(os.path.dirname(__file__) + "/xml_ua.ini")
        self.xmlMP: dict = dict(self.dataINI['Multipolygons'])
        self.xmlPL: str = self.dataINI['Polylines']['adjacent']
        self.xmlPoints: list = []
        self.qgisPoints: dict = {}
        self.qgisLines: dict = {}
        self.xmlLines: list = []
        self.ULIDs: list = []
        self.qgisLines = {}
        self.DMs: list = ['Survey','GPS','Digitization','Photogrammetry']
        
        self.createGroup()
        self.importPoints()
        self.importPickets()
        self.importLines()
        self.importZone()
        self.importQuartal()
        self.importParcel()
        
    def createGroup(self):
        '''
            При відкритті файлу xml з диску, різні файли можуть мати
            однакові імена у папці і різні шляхи.
            Оскільки шляхи довгі вони не можуть використовуватись 
            для іменування групи
        '''
        # logging(common.logFile)
        self.group_name = f"{self.fileNameNoExt}::{str(self.id)}"
        self.group = self.layers_root.findGroup(self.group_name)
        
        if self.group:
            self.layers_root.removeChildNode(self.group)
            # logging(common.logFile, "\n\t" + f"Групу '{self.group_name}' видалено.")
            pass
        else:
            # logging(common.logFile, "\n\t" + f"Групу '{self.group_name}' не знайдено.")
            pass

        self.group = self.layers_root.addGroup(self.group_name)
        # logging(common.logFile, "\n\t" + f"Групу '{self.group_name}' створено.")
        cloned_group = self.group.clone()
        self.layers_root.removeChildNode(self.group)
        self.layers_root.insertChildNode(0, cloned_group)
        
        self.layers = QgsProject.instance().mapLayers().values()
        self.layers_root = QgsProject.instance().layerTreeRoot()
        
        return
        
    def importPoints(self):

        # logging(common.logFile)
        self.xmlPoints = []
        self.qgisPoints = {}
        
        for point in self.root.findall(".//PointInfo/Point"):
            uidp = point.find("UIDP").text if point.find("UIDP") is not None else None
            pn = point.find("PN").text if point.find("PN") is not None else None
            for DM in self.DMs:
                dm = point.find("DeterminationMethod/" + DM)
                if dm is None :
                    # logging(common.logFile, " dmt: " + 'NoneType')
                    pass
                else:
                    dmt = dm.tag
                    # logging(common.logFile, " dmt: '" + dmt + "'")
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
            
        # logstr = ''
        # for uidp, point in self.qgisPoints.items():
            # logstr += '\n\t' + f"'{uidp}' {XY(point)}" 
        # logging(common.logFile, "\n   UIDP Point" + logstr)
            
        return
        
    def importLines(self):
        
        # logging(common.logFile)
        self.qgisLines = {}
        self.xmlLines = []
        
        logstr = ''
        for line in self.root.findall(".//PL"):
            
            ulid = line.find("ULID").text
            if ulid is None: continue
            points = [p.text for p in line.findall(".//P")]
            logstr += '\n\t "' + ulid + '" ' + str(points)
                
            length = line.find("Length").text if line.find("Length") is not None else None
            self.xmlLines.append({
                "ULID": ulid,
                "Points": points,
                "Length": length
            })
            
            self.qgisLines[ulid] = [self.qgisPoints[uidp] for uidp in points ]
        # logging(common.logFile, "\n    ULID [Point list]:" + logstr )
            
        return

    def linesToCoordinates(self, lines_element):
        """
        Формує список координат замкненого полігону на основі ULID ліній і їх точок.
    
        Parameters:
            lines_element (xml.etree.ElementTree.Element): Елемент, який містить піделементи <Line>.
            self.qgisLines (dict): Словник, де ключ — ULID (унікальний ідентифікатор), 
                                а значення — список координат [(x1, y1), (x2, y2)].
                                
        Returns:
            list: Список координат замкненого полігону.
        """
        # logging(common.logFile, "\n\t" + str(lines_element))
        if lines_element is None:
            raise ValueError("lines_element не може бути None.")
    
        # Зчитати всі ULID ліній
        lines = []
        
        logstr = ''
        for line in lines_element.findall(".//Line"):
            ulid = line.find("ULID").text
            logstr += '\n\t"' + ulid + '" '+ str(line)

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
            elif ulid:
                raise ValueError(f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError("Лінія не містить атрибуту унікального ідентифікатора.")
        # logging(common.logFile, "\n   ULID:" + logstr)
    
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
        logstr = ''
        i = 0
        for point in coordinates:
            i += 1
            logstr += f"\n\t {str(i)}. {XY(point)}"
        # logging(common.logFile, "\n\tcoordinates: " + logstr)
        
        line_string = QgsLineString([QgsPointXY(y, x) for x, y in coordinates])

        polygon = QgsPolygon()
        polygon.setExteriorRing(line_string)  # Додавання зовнішнього кільця
        return polygon

    def importParcel(self):
        
        # logging(common.logFile)
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
        # logging(common.logFile, "\n\tparcel_id = " + parcel_id)

        for parcel in self.root.findall(".//Parcels/ParcelInfo/ParcelMetricInfo"):
            
            # Зовнішні межі
            externals_element = parcel.find(".//Externals/Boundary/Lines")
            # logging(common.logFile, "\n\t.//Externals/Boundary/Lines\n\t" + str(externals_element))
            if externals_element is not None:
                external_coords = self.linesToCoordinates(externals_element)

                logstr = ''
                i = 0
                for point in external_coords:
                    i += 1
                    logstr += f"\n\t {str(i)}. {XY(point)}"
                # logging(common.logFile, "\n\t external_coords: " + logstr)
            
            internals_element = parcel.find(".//Internals/Boundary/Lines")
            # logging(common.logFile, "\n\t.//Internals/Boundary/Lines\n\t" + str(externals_element))
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
        
        QgsProject.instance().addMapLayer(layer)

    def get_full_name(self, person_element):
        
        # logging(common.logFile)
        if person_element is None:
            return ""  # Якщо елемент не знайдено, повертаємо порожній рядок
    
        # Отримуємо окремі частини і перевіряємо, чи вони існують
        last_name = person_element.find("LastName").text if person_element.find("LastName") is not None else ""
        first_name = person_element.find("FirstName").text if person_element.find("FirstName") is not None else ""
        middle_name = person_element.find("MiddleName").text if person_element.find("MiddleName") is not None else ""
    
        # Формуємо повне ім'я
        full_name = f"{last_name} {first_name} {middle_name}".strip()
        return full_name

    def importQuartal(self):
        
        # logging(common.logFile)
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

        # for quarter_num, contacts in quarter_info.items():
            # logging(common.logFile, "\n\t" + f"  Квартал: {quarter_num}")
            # logging(common.logFile, "\n\t" + f"  Голова місцевої влади: {contacts['LocalAuthorityHead']}")
            # logging(common.logFile, "\n\t" + f"  Голова ДКЗР: {contacts['DKZRHead']}")
            

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
            # logging(common.logFile, "\n\t.//Externals/Boundary/Lines\n\t" + str(externals_element))
            if externals_element is not None:
                external_coords = self.linesToCoordinates(externals_element)

                logstr = ''
                i = 0
                for point in external_coords:
                    i += 1
                    logstr += f"\n\t {str(i)}. {XY(point)}"
                # logging(common.logFile, "\n\t external_coords: " + logstr)
            
            internals_element = quarter.find(".//Internals/Boundary/Lines")
            # logging(common.logFile, "\n\t.//Internals/Boundary/Lines\n\t" + str(externals_element))
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
        
            # logging(common.logFile, "\n\t" + f"Auth Head: {auth_head_full_name}")
            # logging(common.logFile, "\n\t" + f"DKZR Head: {dkzr_head_full_name}")

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
        
        QgsProject.instance().addMapLayer(layer)
        
    def importZone(self):
        
        # logging(common.logFile)
        layer = QgsVectorLayer("MultiPolygon?crs=" + self.crsEpsg, "Кадастрова зона", "memory")
        layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/zone.qml")
        layer_provider = layer.dataProvider()
        layer_provider.addAttributes([
            QgsField("CadastralZoneNumber", QVariant.String)  # Ідентифікатор зони
        ])
        layer.updateFields()
        
        zone_ne = self.root.find(".//CadastralZoneInfo/CadastralZoneNumber")
        zone_id = zone_ne.text
        # logging(common.logFile, "\n\tzone_id = " + str(zone_id))
    
        for zone in self.root.findall(".//CadastralZoneInfo"):
            
            # Зовнішні межі
            externals_element = zone.find(".//Externals/Boundary/Lines")
            # logging(common.logFile, "\n\t.//Externals/Boundary/Lines\n\t" + str(externals_element))
            if externals_element is not None:
                external_coords = self.linesToCoordinates(externals_element)

                # logstr = ''
                # i = 0
                # for point in external_coords:
                    # i += 1
                    # logstr += f"\n\t {str(i)}. {XY(point)}"
                # logging(common.logFile, "\n\t external_coords: " + logstr)
            
            internals_element = zone.find(".//Internals/Boundary/Lines")
            # logging(common.logFile, "\n\t.//Internals/Boundary/Lines\n\t" + str(externals_element))
            internal_coords_list = []
            if internals_element is not None:
                internal_coords_list.append(self.linesToCoordinates(internals_element))
    
            polygon = self.coordToPolygon(external_coords)
            for internal_coords in internal_coords_list:
                polygon.addInteriorRing(internal_coords)
            
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(polygon))
            feature.setAttributes([zone_id])
            layer_provider.addFeature(feature)
        
        QgsProject.instance().addMapLayer(layer)
        
    def removeLayer(self, new_layer):
        
        # logging(common.logFile, "\n\t" + new_layer)
    
        layers_to_remove = [layer for layer in self.project.mapLayers().values() if layer.name() == new_layer]

        if layers_to_remove:
            n_layers = len(layers_to_remove)
            # logging(common.logFile,  "\n\t" + f" Буде видалено {str(n_layers)} шарів." )
            for layer in layers_to_remove:
                self.project.removeMapLayer(layer.id())
        else:
            # logging(common.logFile,  "\n\t" + " Нема шарів для видалення." )
            pass
            
    def importPickets(self):

        layer_name = "Пікети"
        # logging(common.logFile, "\n\tlayer_name = " + layer_name)
        self.removeLayer(layer_name)
        layer = QgsVectorLayer("Point?crs=" + self.crsEpsg, layer_name, "memory")
        
        if layer.isValid():
            layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/points.qml")
            # Це додає шар до проєкту, але не до дерева шарів.
            QgsProject.instance().addMapLayer(layer)        
        else:
            QMessageBox.critical(self, "xml_ua", "Виникла помилка при створенні шару точок.")
            
        # Вузол дозволяє інтегрувати шар у дерево шарів.
        layer_node = self.layers_root.findLayer(layer.id())
        self.group = self.layers_root.findGroup(self.group_name)
        if not layer_node:
            print("Не вдалося знайти вузол шару в дереві.")
        else:
            # Перемістити шар до групи
            self.group.insertChildNode(0, layer_node.clone())
            # self.layers_root.removeChildNode(layer_node)
            self.layers_root.removeChildNode(layer_node)  # Видалити з поточного місця
            # self.group.addChildNode(layer_node)   # Додати до групи
            # logging(common.logFile, "\n\t" + f"Шар '{layer_name}' додано до групи '{self.group_name}'.")
        
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
        
    def importLinesXML(self):

        logging(common.logFile)
        layer_name = "Лінії XML"
        # logging(common.logFile, " layer_name = " + layer_name)
        self.removeLayer(layer_name)
        layer = QgsVectorLayer("LineString?crs=" + self.crsEpsg, layer_name, "memory")
        
        if layer.isValid():
            layer.loadNamedStyle(os.path.dirname(__file__) + "/templates/lines.qml")
            # додаємо шар до проекту
            QgsProject.instance().addMapLayer(layer)        
        else:
            QMessageBox.critical(self, "xml_ua", "Виникла помилка при створенні шару ліній.")
            
        provider = layer.dataProvider()
        provider.addAttributes([QgsField("ULID", QVariant.String)])
        provider.addAttributes([QgsField("Length", QVariant.String)])
        layer.updateFields()
        
        self.qgisLines = {}
        for point in self.root.findall(".//Point"):
            uidp = point.find("UIDP").text
            x = float(point.find("X").text)
            y = float(point.find("Y").text)
            self.qgisLines[uidp] = QgsPointXY(y, x)
            # logging(common.logFile, " self.qgisLines[" + uidp + "] = " + str(self.qgisLines[uidp]))

        # Додаємо полілінії на шар
        for pl in self.root.findall(".//PL"):
            point_ids = [p.text for p in pl.find("Points").findall("P")]
            line_ULID = pl.find("ULID")
            line_length = pl.find("Length")
            # logging(common.logFile, " line_ULID = " + line_ULID.text)
            polyline_points = [self.qgisLines[pid] for pid in point_ids if pid in self.qgisLines]
            fields = layer.fields()
            feature = QgsFeature(fields)
            feature["ULID"] = line_ULID.text
            feature["Length"] = line_length.text
            # logging(common.logFile, " feature['ULID'] = " + feature["ULID"])
            feature.setGeometry(QgsGeometry.fromPolylineXY(polyline_points))
            provider.addFeatures([feature])
            layer.updateExtents()
        return

def caller():
    return inspect.stack()[2].function

def logging(logFile, msg=""):
    logFile.write(f"<.{os.path.basename(__file__)}:{sys._getframe().f_back.f_lineno}> {caller()}(): {msg}\n")
    logFile.flush()

def log_dict(logFile, dict, name: str = ""):
    msg = f"{name}:"
    for key, value in dict.items():
        msg += '\n\t' + f"{key}: {value}"
    logFile.write(f"{sys._getframe().f_back.f_lineno}: {caller()}: {msg}\n")
    logFile.flush()






























