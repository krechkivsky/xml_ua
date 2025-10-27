# -*- coding: utf-8 -*-
# layers.py

#✔️ 2025.10.02 15:09 Закриття останньої вкладки по натисканню кнопки закриття не відбувається, 
# а потрібно щоб по натисканню кнопки закриття остання вкладка закривалася і 
# видалялася відповідна їй група шарів

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
#from xml.etree import ElementTree as ET
from .common import logFile
from .common import log_msg
from .common import category_map
from .common import purpose_map
from .common import code_map
from .common import parcel_field2path_dict
from .topology import GeometryProcessor
from .common import area_determination_map
from .points import Points
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
                plugin=None,
                xml_data=None):

        # xmlFilePath - для формування назви групи шарів
        # tree        - розпарсене дерево xml
        # plugin      _ для підключення обробника редагування геометрії

        # __init__  виклик конструктора з dockwidget.py:process_action_open
        # обох викликах tree розпарсений
        
        self.xml_data = xml_data # Store the xml_data object
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

        # Перевіряємо, чи група з такою назвою вже існує
        existing_group = self.layers_root.findGroup(self.fileNameNoExt)
        if existing_group:
            self.group_name = self.fileNameNoExt
            self.group = existing_group
            #log_msg(logFile, f"Використовується існуюча група: '{self.group_name}'")
        else:
            # генеруємо унікальне ім'я групи шарів, в яку будуть поміщені шари xml
            self.group_name = self.generate_group_name(self.fileNameNoExt)
            self.create_group()

        if tree is None:
            self.tree = ET.parse(self.xmlFilePath)
        else:
            self.tree = tree
        # Корінь дерева xml
        self.root = self.tree.getroot()

        self.under_construction = self.check_construction_status()

        self.project = QgsProject.instance()
        self.crs = self.project.crs()
        self.crsEpsg = self.crs.authid()
        self.added_layers = []
        
        # Set custom property on the group itself
        if self.group:
            self.group.setCustomProperty("xml_data_group_name", self.group_name)
            if self.xml_data:
                self.group.setCustomProperty("xml_data_object_id", id(self.xml_data))
                # #log_msg(logFile, f"Встановлено custom property на групу '{self.group_name}' з ID xml_data: {id(self.xml_data)}")

        self.points_handler = Points(self.root, self.crsEpsg, self.group, self.plugin_dir, self.layers_root)
        self.points_handler.read_points()

        self.lines_handler = PLs(self.root, self.crsEpsg, self.group, self.plugin_dir, self.layers_root, self.points_handler.qgisPoints)
        self.lines_handler.read_lines()
        self.qgisLines = self.lines_handler.qgis_lines # Keep for other methods

        # --- Початок змін: Ініціалізація змінних для уникнення UnboundLocalError ---
        lands_handler = None
        leases_handler = None
        subleases_handler = None
        restrictions_handler = None
        quarter_handler = None
        zone_handler = None
        parcel_handler = None
        self.adjacents_handler = None
        # --- Кінець змін ---
 
        # --- Початок змін: Створення шарів у правильному порядку (зверху вниз) ---
        # Кожен новий шар додається на позицію 0 (наверх групи).
        zone_handler = CadastralZoneInfo(self.root, self.crsEpsg, self.group, self.plugin_dir, self.linesToCoordinates, self, xml_data=self.xml_data) # Кадастрова зона
        zone_handler.add_zone_layer()

        quarter_handler = CadastralQuarters(self.root, self.crsEpsg, self.group, self.plugin_dir, self.linesToCoordinates, self, xml_data=self.xml_data)
        quarter_handler.add_quarter_layer()

        parcel_handler = CadastralParcel(self.root, self.crsEpsg, self.group, self.plugin_dir, self.layers_root, self.linesToCoordinates, self, xml_data=self.xml_data)
        parcel_handler.add_parcel_layer()

        lands_handler = LandsParcels(self.root, self.crsEpsg, self.group, self.plugin_dir, self.layers_root, self.linesToCoordinates, self, xml_data=self.xml_data) # Угіддя
        if self.root.find(".//LandsParcel") is not None:
            lands_handler.add_lands_layer()

        leases_handler = Leases(self.root, self.crsEpsg, self.group, self.plugin_dir, self.linesToCoordinates, self, xml_data=self.xml_data) # Оренда
        if self.root.find(".//Leases") is not None:
            leases_handler.add_leases_layer()

        subleases_handler = Subleases(self.root, self.crsEpsg, self.group, self.plugin_dir, self.linesToCoordinates, self, xml_data=self.xml_data) # Суборенда
        if self.root.find(".//Subleases") is not None:
            subleases_handler.add_subleases_layer()

        restrictions_handler = Restrictions(self.root, self.crsEpsg, self.group, self.plugin_dir, self.linesToCoordinates, self, xml_data=self.xml_data) # Обмеження
        if self.root.find(".//Restrictions") is not None:
            restrictions_handler.add_restrictions_layer()

        self.adjacents_handler = AdjacentUnits(self.root, self.crsEpsg, self.group, self.plugin_dir, self, xml_data=self.xml_data) # Суміжники
        if self.root.find(".//AdjacentUnits") is not None:
            self.adjacents_handler.add_adjacents_layer()

        # --- Початок змін: Виправлення порядку шарів "Вузли" та "Полілінії" ---
        self.lines_handler.add_lines_layer() # Полілінії
        self.points_handler.add_pickets_layer() # Вузли
        # --- Кінець змін ---

        # --- Початок змін: Формування списку з перевіркою на None ---
        all_handlers = [
            self.points_handler, self.lines_handler, quarter_handler, zone_handler,
            parcel_handler, lands_handler, leases_handler, subleases_handler,
            restrictions_handler, self.adjacents_handler
        ]
        # Set custom property on each layer created by handlers
        # --- Кінець змін ---
        for layer_obj in all_handlers:
            if layer_obj and hasattr(layer_obj, 'layer') and layer_obj.layer and self.xml_data: # Assuming each handler has a 'layer' attribute
                layer_obj.layer.setCustomProperty("xml_data_object_id", id(self.xml_data))
                # #log_msg(logFile, f"Встановлено custom property на шар '{layer_obj.layer.name()}' з ID xml_data: {id(self.xml_data)}")
        # --- Кінець змін ---

    def check_construction_status(self):
        """
        Перевіряє, чи XML-файл "у розробці", перевіряючи наявність ключових елементів.
        """
        # #log_msg(logFile)
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
                #log_msg(logFile, f"Елемент не знайдено: {path}. Файл у розробці.")
                return True

        # #log_msg(logFile, "Всі необхідні елементи знайдено. Файл не в розробці.")
        return False
    def generate_group_name(self, base_name):

        """
        Формує назву групи на основі базової назви, додаючи суфікс, якщо група з такою назвою вже існує.
        """

        group_name = base_name

        existing_groups = [group.name() for group in self.layers_root.findGroups()]

        if group_name not in existing_groups:
            # log_calls(logFile, f"group_name = {group_name}")
            return group_name

        suffix = 1
        while f"{base_name}#{suffix}" in existing_groups:
            suffix += 1

        group_name = f"{base_name}#{suffix}"
        #log_msg(logFile, f"group_name = {group_name}")
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
        self.group = self.layers_root.addGroup(self.group_name)
        cloned_group = self.group.clone()
        self.layers_root.removeChildNode(self.group)
        self.layers_root.insertChildNode(0, cloned_group)
        self.group = cloned_group

        # оновлення шарів та кореня дерева шарів
        self.layers = QgsProject.instance().mapLayers().values()
        self.layers_root = QgsProject.instance().layerTreeRoot()

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

        if lines_element is None:
            raise ValueError("lines_element не може бути None.")

        # Зчитати всі ULID ліній
        lines = []

        logstr = ''
        i = 0
        for line in lines_element.findall(".//PL"):
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

    def get_full_name(self, person_element):

        # #log_msg(logFile)

        if person_element is None:
            return ""  # Якщо елемент не знайдено, повертаємо порожній рядок

        # Отримуємо окремі частини і перевіряємо, чи вони існують
        last_name = person_element.find("LastName").text if person_element.find("LastName") is not None else ""
        first_name = person_element.find("FirstName").text if person_element.find("FirstName") is not None else ""
        middle_name = person_element.find("MiddleName").text if person_element.find("MiddleName") is not None else ""

        # Формуємо повне ім'я
        full_name = f"{last_name} {first_name} {middle_name}".strip()
        return full_name

    def on_editing_stopped(self):
        """Обробник сигналу editingStopped."""
        #✔️ 2025.05.19 функція може бути викликана з будь-якого шару
        # викликається при зміні як атрибутів, так і геометрії об'єкта
        # означає що редагування зупинено і зміни у дереві xml
        # треба зберегти у файл xml
        #log_msg(logFile, f"Зміни збережено у файлі {self.xmlFilePath}.")
        self.layer_modified = True
        self.tree.write(self.xmlFilePath, encoding="utf-8", xml_declaration=True) # type: ignore
        self.show_message("on_editing_stopped", f"Зміни збережено у файлі {self.xmlFilePath}.")


    def handle_parcel_attribute_change(self, layer, fid, field_index, new_value):

        field_name = layer.fields()[field_index].name()
        #log_msg(logFile, f"Зміна значення поля №{field_name} на {new_value}")
    
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
            #log_msg(logFile, f"Зміна способу визначення площі на {new_value}")
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
                #log_msg(logFile, f"Спосіб визначення площі ділянки змінено на {new_value}")
                # self.show_message("handle_parcel_attribute_change:", f"Спосіб визначення площі ділянки змінено на {new_value}")
                # Оновлюємо XML
                self.update_area_determination_in_tree(new_value)
            return # інші значення "Спосіб визначення площі"

        # тут починається обробка змін полів відмінних від "Спосіб визначення площі"

        if field_name == "ParcelID":
            #log_msg(logFile, f"Зміна ParcelID на {new_value}")
            # Блокує QGIS
            # layer.changeAttributeValue(fid, field_index, new_value)
            element_path = "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/ParcelID"
            element = self.tree.find(element_path)
            if element is None:
                #log_msg(logFile, f"Елемент за шляхом {element_path} не знайдено❗")
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
        #log_msg(logFile, f"{new_value}")
        # Шлях до елемента, який потрібно змінити відомий:
        element_path = ".//ParcelMetricInfo/Area/DeterminationMethod"
        element = self.tree.find(element_path)
        if element is None:
            #log_msg(logFile, f"Елемент за шляхом {element_path} не знайдено❗")
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

            #log_msg(logFile, f"new_value = {new_value}")

            if new_value.startswith("Переобчислення з 'SC63"):
                zona = new_value[-2]
                #log_msg(logFile, f"zona = {zona}")
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

        # #log_msg(logFile)

        if person_element is None:
            return ""  # Якщо елемент не знайдено, повертаємо порожній рядок

        # Отримуємо окремі частини і перевіряємо, чи вони існують
        last_name = person_element.find("LastName").text if person_element.find("LastName") is not None else ""
        first_name = person_element.find("FirstName").text if person_element.find("FirstName") is not None else ""
        middle_name = person_element.find("MiddleName").text if person_element.find("MiddleName") is not None else ""

        # Формуємо повне ім'я
        full_name = f"{last_name} {first_name} {middle_name}".strip()
        return full_name
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
        root = QgsProject.instance().layerTreeRoot()

        if group_name is None or group_name == "":
            parent = root
        else:
            parent = root.findGroup(group_name)
            if parent is None:
                #log_msg(logFile, f"'{group_name}' не знайдена. \nШар '{layer_name}' не видалено.")
                return

        # Знаходимо шар у батьківському вузлі (групі або корені) за іменем
        for child in parent.children():
            # Перевіряємо, чи вузол все ще валідний перед доступом до його властивостей
            if child and isinstance(child, QgsLayerTreeLayer) and child.name() == layer_name:
                # Видалення вузла з дерева автоматично видалить і шар з проекту,
                # якщо на нього більше не буде посилань.
                parent.removeChildNode(child)
                #log_msg(logFile, f"Вузол шару '{layer_name}' видалено з групи '{group_name}'.")
                return # Виходимо, оскільки вузол знайдено та видалено.

    def add_lands(self):
        """
        Цей метод застарів і перенесений до dockwidget.py.
        """
        pass
    def lines_element2polygone(self, lines_element): # Останній варіант
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
        # #log_msg(logFile, "\nlines: \n" + logstr)

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
        # #log_msg(logFile, "polyline_coordinates (x, y): \n" + log_str)

        return polyline
