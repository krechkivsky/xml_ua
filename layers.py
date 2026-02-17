

import os
import xml.etree.ElementTree as ET

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
from qgis.PyQt.QtWidgets import QInputDialog

from lxml import etree as ET

from .common import logFile
from .common import log_msg
from .common import category_map
from .common import purpose_map
from .common import code_map
from .common import parcel_field2path_dict
from .data_models import xml_data
from .topology import GeometryProcessor
from .common import area_determination_map
from .points import Points
from .control_point import ControlPoint
from .lines import PLs
from .zone import CadastralZoneInfo
from .quarters import CadastralQuarters
from .parcels import CadastralParcel
from .lands import LandsParcels
from .leases import Leases
from .subleases import Subleases
from .restrictions import Restrictions
from .adjacents import AdjacentUnits


class xmlUaLayers:

    _id_counter = 0

    def __init__(self,
                 xmlFilePath="",
                 tree=None,
                 plugin=None,
                 xml_data=None,
                 context="open"):

        self.xml_data = xml_data  # Store the xml_data object
        self.cleanup()

        self.plugin = plugin
        self.context = context

        xmlUaLayers._id_counter += 1

        self.id = xmlUaLayers._id_counter

        self.block_attribute_handling = False

        self.xml_data_changed = False

        self.layer_colors = {}

        self.layers = QgsProject.instance().mapLayers().values()

        self.layers_root = QgsProject.instance().layerTreeRoot()

        self.xmlFilePath: str = xmlFilePath
        self.plugin_dir = os.path.dirname(__file__)
        self.fileNameNoExt: str = os.path.splitext(
            os.path.basename(xmlFilePath))[0]

        existing_group = None
        preferred_group_name = ""
        if self.xml_data is not None:
            preferred_group_name = str(getattr(self.xml_data, "group_name", "") or "").strip()

        if preferred_group_name:
            existing_group = self.layers_root.findGroup(preferred_group_name)
            if existing_group:
                self.group_name = preferred_group_name
                self.group = existing_group
            else:


                self.group_name = preferred_group_name
                self.create_group()
                existing_group = self.group

        if not existing_group:
            existing_group = self.layers_root.findGroup(self.fileNameNoExt)
            if existing_group:
                self.group_name = self.fileNameNoExt
                self.group = existing_group

        if not existing_group:
            self.group_name = self.generate_group_name(self.fileNameNoExt)
            self.create_group()

        if tree is None:
            self.tree = ET.parse(self.xmlFilePath)
        else:
            self.tree = tree

        self.root = self.tree.getroot()

        self.under_construction = self.check_construction_status()

        self.project = QgsProject.instance()
        self.crs = self.project.crs()
        self.crsEpsg = self.crs.authid()
        self.added_layers = []

        if self.group:
            self.group.setCustomProperty(
                "xml_data_group_name", self.group_name)
            if self.xml_data:
                self.group.setCustomProperty(
                    "xml_data_object_id", id(self.xml_data))

        self.points_handler = Points(
            self.root, self.crsEpsg, self.group, self.plugin_dir, self.layers_root)
        self.points_handler.read_points()

        self.lines_handler = PLs(self.root, self.crsEpsg, self.group,
                                 self.plugin_dir, self.layers_root, self.points_handler.qgisPoints)
        self.lines_handler.read_lines()
        self.qgisLines = self.lines_handler.qgis_lines  # Keep for other methods

        lands_handler = None
        leases_handler = None
        self.subleases_handler = None
        restrictions_handler = None
        quarter_handler = None
        zone_handler = None
        parcel_handler = None
        self.adjacents_handler = None

        self.points_handler.add_pickets_layer()  # Вузли

        self.control_points_handler = ControlPoint(
            self.root,
            self.crsEpsg,
            self.group,
            self.plugin_dir,
            self.layers_root,
            points_handler=self.points_handler,
            xml_data=self.xml_data,
        )
        self.control_points_handler.add_control_points_layer()  # Закріплені вузли
        self.lines_handler.add_lines_layer()  # Полілінії

        zone_handler = CadastralZoneInfo(self.root, self.crsEpsg, self.group,
                                         self.plugin_dir, self.linesToCoordinates, self, xml_data=self.xml_data)
        zone_handler.add_zone_layer()

        quarter_handler = CadastralQuarters(
            self.root, self.crsEpsg, self.group, self.plugin_dir, self.linesToCoordinates, self, xml_data=self.xml_data)
        quarter_handler.add_quarter_layer()

        parcel_handler = CadastralParcel(self.root, self.crsEpsg, self.group, self.plugin_dir,
                                         self.layers_root, self.linesToCoordinates, self, xml_data=self.xml_data)
        parcel_handler.add_parcel_layer()

        lands_handler = LandsParcels(self.root, self.crsEpsg, self.group, self.plugin_dir,
                                     self.layers_root, self.linesToCoordinates, self, xml_data=self.xml_data)
        if self.root.find(".//LandsParcel") is not None:
            lands_handler.add_lands_layer()

        leases_handler = Leases(self.root, self.crsEpsg, self.group, self.plugin_dir,
                                self.linesToCoordinates, self, xml_data=self.xml_data)  # Оренда
        if self.root.find(".//Leases") is not None:
            leases_handler.add_leases_layer()

        self.subleases_handler = Subleases(self.root, self.crsEpsg, self.group, self.plugin_dir,
                                           self.linesToCoordinates, self, xml_data=self.xml_data)  # Суборенда
        if self.root.find(".//Subleases") is not None:
            self.subleases_handler.add_subleases_layer()

        restrictions_handler = Restrictions(self.root, self.crsEpsg, self.group, self.plugin_dir,
                                            self.linesToCoordinates, self, xml_data=self.xml_data)  # Обмеження
        if self.root.find(".//Restrictions") is not None:
            restrictions_handler.add_restrictions_layer()

        self.adjacents_handler = AdjacentUnits(
            self.root, self.crsEpsg, self.group, self.plugin_dir, self, self.xml_data)
        if self.root.find(".//AdjacentUnits") is not None:
            self.adjacents_handler.add_adjacents_layer()

        all_handlers = [
            self.points_handler, self.control_points_handler, self.lines_handler, quarter_handler, zone_handler,
            parcel_handler, lands_handler, leases_handler, self.subleases_handler,
            restrictions_handler, self.adjacents_handler
        ]

        for layer_obj in all_handlers:

            if layer_obj and hasattr(layer_obj, 'layer') and layer_obj.layer and self.xml_data:
                layer_obj.layer.setCustomProperty("xml_data_object_id", str(
                    id(self.xml_data)))  # Ensure it's a string

                layer_obj.layer.setCustomProperty(
                    "xml_group_name", self.group_name)

    def check_construction_status(self):
        """
        Перевіряє, чи XML-файл "у розробці", перевіряючи наявність ключових елементів.
        """

        paths_to_check = [
            "./AdditionalPart/ServiceInfo",
            "./AdditionalPart/InfoLandWork",
            "./InfoPart/MetricInfo",
            "./InfoPart/CadastralZoneInfo",
            "./InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo",
            ".//ParcelInfo",
            ".//ParcelInfo/LandsParcel",
            ".//ParcelInfo/AdjacentUnits"
        ]

        for path in paths_to_check:
            if self.root.find(path) is None:

                return True

        return False

    def generate_group_name(self, base_name):
        """
        Формує назву групи на основі базової назви, додаючи суфікс, якщо група з такою назвою вже існує.
        """

        group_name = base_name

        existing_groups = [group.name()
                           for group in self.layers_root.findGroups()]

        if group_name not in existing_groups:

            return group_name

        suffix = 1
        while f"{base_name}#{suffix}" in existing_groups:
            suffix += 1

        group_name = f"{base_name}#{suffix}"

        return group_name

    def cleanup(self):
        """
        Очищує ресурси, пов'язані з попереднім екземпляром,
        щоб уникнути дублювання при перезавантаженні плагіна.
        """

        if hasattr(self, 'group') and self.group:

            if self.layers_root.findGroup(self.group.name()):
                self.layers_root.removeChildNode(self.group)
            self.group = None

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
        self.group = self.layers_root.addGroup(self.group_name)
        cloned_group = self.group.clone()
        self.layers_root.removeChildNode(self.group)
        self.layers_root.insertChildNode(0, cloned_group)
        self.group = cloned_group

        self.layers = QgsProject.instance().mapLayers().values()
        self.layers_root = QgsProject.instance().layerTreeRoot()

        return

    def linesToCoordinates(self, lines_element):
        """ Формує список координат замкненого полігону на основі ULID ліній 
            і їх точок.

            Parameters:
                lines_element (xml.etree.ElementTree.Element): 
                context (str, optional): Контекст виклику ('open', 'new', 'modify').
                                         Defaults to "unknown".

            Returns:
                list: Список координат замкненого полігону.
        """

        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        lines = []

        for line in lines_element.findall(".//Line"):
            ulid = line.find("ULID").text
            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
            elif ulid:
                raise ValueError(
                    f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError(
                    "Лінія не містить атрибуту унікального ідентифікатора.")

        if not lines:
            return []

        polygon_coordinates = []
        used_lines = set()
        current_line = lines[0]

        polygon_coordinates.extend(current_line[1])
        used_lines.add(current_line[0])

        while len(used_lines) < len(lines):

            for ulid, coords in lines:
                if ulid in used_lines:
                    continue

                if coords[0] == polygon_coordinates[-1]:
                    polygon_coordinates.extend(coords[1:])
                    used_lines.add(ulid)
                    break

                elif coords[-1] == polygon_coordinates[-1]:
                    polygon_coordinates.extend(reversed(coords[:-1]))
                    used_lines.add(ulid)
                    break
            else:
                raise ValueError(
                    "Неможливо сформувати замкнений полігон — деякі лінії не з'єднуються.")

        if polygon_coordinates[0] != polygon_coordinates[-1]:
            polygon_coordinates.append(polygon_coordinates[0])

        return polygon_coordinates

    def on_editing_stopped(self):
        """Обробник сигналу editingStopped."""

        self.layer_modified = True
        self.tree.write(self.xmlFilePath, encoding="utf-8",
                        xml_declaration=True)  # type: ignore
        self.show_message("on_editing_stopped",
                          f"Зміни збережено у файлі {self.xmlFilePath}.")

    def handle_parcel_attribute_change(self, layer, fid, field_index, new_value):

        field_name = layer.fields()[field_index].name()

        if self.block_attribute_handling:
            return

        if layer.customProperty("xml_layer_id") != self.id:
            return

        if field_name == "DeterminationMethod":

            if new_value == "Переобчислення з місцевої системи координат":

                msk_number, ok = QInputDialog.getText(
                    None,
                    "Реєстраційний номер МСК",
                    "Введіть номер місцевої системи координат (наприклад, 4610102):"
                )
                if ok and msk_number.strip():

                    new_label = f"Переобчислення з місцевої системи координат МСК {msk_number.strip()}"

                    layer.blockSignals(True)

                    self.show_message(
                        "Спосіб обчислення площі ділянки:", new_label)
                    layer.changeAttributeValue(fid, field_index, new_label)

                    layer.blockSignals(False)

                    self.update_area_determination_in_tree(new_label)

                    layer.triggerRepaint()
                else:
                    log_msg(logFile, "Номер МСК не введено — зміна скасована❗")
                return  # "Спосіб визначення площі" -> МСК
            else:

                self.update_area_determination_in_tree(new_value)
            return  # інші значення "Спосіб визначення площі"

        if field_name == "ParcelID":

            element_path = "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/ParcelID"
            element = self.tree.find(element_path)
            if element is None:

                return

            element.text = new_value
            self.show_message("handle_parcel_attribute_change:",
                              f"ParcelID змінено на {new_value}")

        return  # інші поля

    def update_area_determination_in_tree(self, new_value):

        element_path = ".//ParcelMetricInfo/Area/DeterminationMethod"
        element = self.tree.find(element_path)
        if element is None:

            return

        for child in list(element):
            element.remove(child)

        if new_value.startswith("Переобчислення з місцевої системи координат"):

            number_MCK = new_value.split(" ")[-1]

            new_element = ET.fromstring(
                f"<Calculation><CoordinateSystem><Local>{number_MCK}</Local></CoordinateSystem></Calculation>")

        else:

            if new_value.startswith("Переобчислення з 'SC63"):
                zona = new_value[-2]

                new_element = ET.fromstring(
                    f"<Calculation><CoordinateSystem><SC63><{zona}/></SC63></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'УСК2000'"):
                new_element = ET.fromstring(
                    "<Calculation><CoordinateSystem><USC2000/></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'WGS84'"):
                new_element = ET.fromstring(
                    "<Calculation><CoordinateSystem><WGS84/></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'СК-42' (6 град зона)"):
                new_element = ET.fromstring(
                    "<Calculation><CoordinateSystem><SC42/></CoordinateSystem></Calculation>")
            if new_value.startswith("Переобчислення з 'СК-42' (3 град зона)"):
                new_element = ET.fromstring(
                    "<Calculation><CoordinateSystem><SC42_3/></CoordinateSystem></Calculation>")
            if new_value.startswith("За координатами обмінного файлу"):
                new_element = ET.fromstring(
                    "<ExhangeFileCoordinates></ExhangeFileCoordinates>")
            if new_value.startswith("Згідно із правовстановлювальним документом"):
                new_element = ET.fromstring("<DocExch></DocExch>")

        element.append(new_element)

    def show_message(self, header, message):
        iface.messageBar().pushMessage(
            header,  # Заголовок
            message,  # Текст повідомлення
            level=Qgis.Success,  # Тип повідомлення (зелений фон)
            duration=0  # 0 секунд — повідомлення буде жити вічно, поки не закриють
        )

    def get_full_name(self, person_element):

        if person_element is None:
            return ""  # Якщо елемент не знайдено, повертаємо порожній рядок

        last_name = person_element.find("LastName").text if person_element.find(
            "LastName") is not None else ""
        first_name = person_element.find("FirstName").text if person_element.find(
            "FirstName") is not None else ""
        middle_name = person_element.find("MiddleName").text if person_element.find(
            "MiddleName") is not None else ""

        full_name = f"{last_name} {first_name} {middle_name}".strip()
        return full_name

    def last_to_first(self, group):
        """Переміщує останній дочірній вузол групи шарів на першу позицію."""
        if group is None:  # noqa
            return

        children = group.children()  # Отримуємо список дочірніх вузлів
        child_count = len(children)  # Отримуємо кількість дочірніх вузлів

        if child_count < 2:
            return

        last_child = children[-1]  # Отримуємо останній дочірній вузол
        cloned_last_child = last_child.clone()  # Клонуємо останній дочірній вузол


        group.insertChildNode(0, cloned_last_child)

        group.removeChildNode(last_child)

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
        root = QgsProject.instance().layerTreeRoot()

        if group_name is None or group_name == "":
            parent = root
        else:
            parent = root.findGroup(group_name)
            if parent is None:

                return

        for child in parent.children():

            if child and isinstance(child, QgsLayerTreeLayer) and child.name() == layer_name:

                parent.removeChildNode(child)

                return  # Виходимо, оскільки вузол знайдено та видалено.

    def add_lands(self):
        """
        Цей метод застарів і перенесений до dockwidget.py.
        """
        pass

    def lines_element2polygone(self, lines_element):  # Останній варіант
        """Формує список координат замкненого полігону на основі ULID ліній
            і їх точок.

            Parameters:
                lines_element (xml.etree.ElementTree.Element):
                Елемент, який містить піделементи <Line>.

            Returns:
                list: Список координат замкненого полігону.
        """

        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//Line"):
            i += 1
            ulid = line.find("ULID").text

            logstr += '\n\t' + ulid + '. '

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
            elif ulid:
                raise ValueError(
                    f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError(
                    "Лінія не містить атрибуту унікального ідентифікатора.")

        if not lines:
            return []

        polygon_coordinates = []
        used_lines = set()
        current_line = lines[0]

        polygon_coordinates.extend(current_line[1])
        used_lines.add(current_line[0])

        while len(used_lines) < len(lines):

            for ulid, coords in lines:
                if ulid in used_lines:
                    continue

                if coords[0] == polygon_coordinates[-1]:
                    polygon_coordinates.extend(coords[1:])
                    used_lines.add(ulid)
                    break

                elif coords[-1] == polygon_coordinates[-1]:
                    polygon_coordinates.extend(reversed(coords[:-1]))
                    used_lines.add(ulid)
                    break
            else:
                raise ValueError(
                    "Неможливо сформувати замкнений полігон — деякі лінії не з'єднуються.")

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

        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//Line"):
            i += 1
            ulid = line.find("ULID").text

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
                coords_str = ", ".join(
                    [f"{point.x():.2f}, {point.y():.2f}" for point in self.qgisLines[ulid]])
                logstr += f"{i}. {ulid}: {coords_str}\n"
            elif ulid:
                raise ValueError(
                    f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError(
                    "Лінія не містить атрибуту унікального ідентифікатора.")
        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//Line"):
            i += 1
            ulid = line.find("ULID").text

            if ulid and ulid in self.qgisLines:
                lines.append((ulid, self.qgisLines[ulid]))
                coords_str = ", ".join(
                    [f"{point.x():.2f}, {point.y():.2f}" for point in self.qgisLines[ulid]])
                logstr += f"{i}. {ulid}: {coords_str}\n"
            elif ulid:
                raise ValueError(
                    f"ULID '{ulid}' не знайдено в списку координат.")
            else:
                raise ValueError(
                    "Лінія не містить атрибуту унікального ідентифікатора.")

        polyline = []

        if not lines:

            QMessageBox.critical(self, "xml_ua", "Нема суміжників.")
            return None

        if len(lines) == 1:
            return self.lines_element2polygone(lines_element)

        polyline.extend([QgsPointXY(point.x(), point.y())
                        for point in lines[0][1]])

        lines.pop(0)

        if not lines:
            return polyline

        while lines:
            found_next_line = False

            for i, (ulid, coords) in enumerate(lines):
                if coords[0] == polyline[-1]:

                    polyline.extend([QgsPointXY(point.x(), point.y())
                                    for point in coords[1:]])
                    lines.pop(i)
                    found_next_line = True
                    break

            if found_next_line:
                continue

            for i, (ulid, coords) in enumerate(lines):
                if coords[-1] == polyline[-1]:

                    polyline.extend([QgsPointXY(point.x(), point.y())
                                    for point in reversed(coords[:-1])])
                    lines.pop(i)
                    found_next_line = True
                    break

            if found_next_line:
                continue

            for i, (ulid, coords) in enumerate(lines):
                if coords[-1] == polyline[0]:

                    polyline = [QgsPointXY(point.x(), point.y())
                                for point in reversed(coords[:-1])] + polyline
                    lines.pop(i)
                    found_next_line = True
                    break

            if found_next_line:
                continue

            for i, (ulid, coords) in enumerate(lines):
                if coords[0] == polyline[0]:

                    polyline = [QgsPointXY(point.x(), point.y())
                                for point in coords[1:]] + polyline
                    lines.pop(i)
                    found_next_line = True
                    break

            if not found_next_line:
                raise ValueError("Полілінія не з'єднана.")

            for i, (ulid, coords) in enumerate(lines):
                if coords[0] == polyline[0]:

                    polyline = [QgsPointXY(point.x(), point.y())
                                for point in coords[1:]] + polyline
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

        return polyline
