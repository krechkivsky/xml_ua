# -*- coding: utf-8 -*-
"""Таблиця метаданих """
import os
import uuid

from datetime import datetime

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtCore import pyqtSignal

from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QMenu
from qgis.PyQt.QtWidgets import QTableView

from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QStandardItemModel

from .date_dialog import DateInputDialog

from .common import logFile
from .common import log_msg
from .common import log_calls
from .common import config
from .common import connector


class TableViewMetadata(QTableView):


    """ Клас таблиці для відображення та роботи з метаданими з обробкою змін.

        Структура таблиці
             0 FileDate
             1 FileGUID
             2 FormatVersion
             3 ReceiverName
             4 ReceiverIdentifier
             5 Software
             6 SoftwareVersion
             7 CoordinateSystem
             8 HeightSystem
             9 MeasurementUnit
            10 CadastralZoneNumber
            11 CadastralQuarterNumber
            12 ParcelID
            13 LocalAuthorityHead
            14 DKZRHead    """

    dataChangedInTable = pyqtSignal(str, str) 

    def __init__(self, parent=None): # after icon click
        """ 
            Initializes the metadata table with custom settings and event handlers.
            Args:
                parent (QWidget, optional): The parent widget. Defaults to None.
            Attributes:
                parent (QWidget): The parent widget.
                table_block_change_flag (bool): Local flag to prevent cyclic changes.
                tooltips (dict): Dictionary containing metadata tooltips.
                items_model (QStandardItemModel): The model for the table items.
            Methods:
                table_right_click: Handles right-click events on the table.
                table_double_click: Handles double-click events on the table.
                table_item_changed: Handles changes to table items.
        """
        super().__init__(parent) 
        # log_msg(logFile, "TableViewMetadata")
        self.parent = parent 
        self.table_block_change_flag = False  # Локальний флаг для запобігання циклічним змінам
        # log_calls(logFile, f"🚩 {self.table_block_change_flag}")

        # Змінити висоту горизонтального заголовка
        self.horizontalHeader().setFixedHeight(30)
        self.verticalHeader().setDefaultSectionSize(30)

        # Підключення обробника правого кліку
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        #self.customContextMenuRequested.connect(self.table_right_click)
        connector.connect(self, "customContextMenuRequested", self.table_right_click)


        # Підключення обробника подвійного кліку
        #self.doubleClicked.connect(self.table_double_click)
        connector.connect(self, "doubleClicked", self.table_double_click)
        self.tooltips = dict(config['metaDataTooltips'])

        # ✔ 2025.01.31 08:41:52
        self.items_model = QStandardItemModel()
        self.setModel(self.items_model)
        self.items_model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        # Підключення обробника змін даних у комірках
        #self.items_model.itemChanged.connect(self.table_item_changed)
        connector.connect(self.items_model, "itemChanged", self.table_item_changed)


    def table_item_changed(self, cell):
        """ 
        Handles the event of changing cells in QStandardItemModel.
        This method determines the full_path and value of the cell where the data has changed,
        and forms the signal dataChangedInTable = pyqtSignal(str, str).
        Args:
            cell (QStandardItem): The cell that has been changed.
        Notes:
            - This method can perform the following processing:
                - Update other components
                - Validate the data
                - Set the background color to red
                - Log the changes
            - Temporarily block the signal using:
                self.items_model.blockSignals(True)  # Disable signals
                self.items_model.blockSignals(False)  # Enable signals
        Logging:
            Logs the cell text and the table_block_change_flag status.
            If table_block_change_flag is set, logs the status and skips the update.
            Otherwise, sets table_block_change_flag to True and performs the update.
        Updates:
            Depending on the tag extracted from full_path, calls the appropriate update method
            on the parent treeViewXML object to update the tree structure.
        Finally:
            Resets the table_block_change_flag to False and logs the reset status.
        """
        # TODO: 2025.01.22 06:41
        #    В методі можна виконати обробку:
        #       - оновлення інших компонентів 
        #       - перевірку валідності
        #       - встановлення червоного фону
        #       - логування змін.
        # TODO:2025.01.22 07:04 тимчасово заблокувати сигнал
        # self.items_model.blockSignals(True) - Вимкнення сигналів
        # self.items_model.blockSignals(False)  # Увімкнення сигналів

        log_msg(logFile, f"{cell.text()}")
        log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")
        if self.table_block_change_flag:
            log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")
            return

        log_msg(logFile, f"встановлюємо table_block_change_flag для блокування змін за межами функції і виконуємо оновлення")
        self.table_block_change_flag = True # TODO: 2025.01.23 12:20 перенести в try: область
        log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")

        try:
            # ✅ 2025.01.30 01:34:57 row i key_cell непотрібні
            # ✅ 2025.01.30 02:09:30 у key_cell знаходиться не тег, а опис тегу з XSD
            # row = cell.row()
            # key_cell = self.items_model.cell(row, 0)
            value = cell.text()
            full_path = cell.data(Qt.UserRole)
            tag = full_path.split("/")[-1]
            log_msg(logFile,f"тег комірки: {tag}")

            # ✅ 2025.01.30 01:35:57 вибір функції для оновлення дерева по останньому тегу
            if tag == "FileDate":
                self.parent.treeViewXML.tree_FileDate_update(full_path[1:], value)
            if tag == "FileGUID":
                self.parent.treeViewXML.tree_FileGUID_update(full_path[1:], value)
            if tag == "FormatVersion":
                self.parent.treeViewXML.tree_FormatVersion_update(full_path[1:], value)
            if tag == "ReceiverName":
                self.parent.treeViewXML.tree_ReceiverName_update(full_path[1:], value)
            if tag == "ReceiverIdentifier":
                self.parent.treeViewXML.tree_ReceiverIdentifier_update(full_path[1:], value)
            if tag == "Software":
                self.parent.treeViewXML.tree_Software_update(full_path[1:], value)
            if tag == "SoftwareVersion":
                self.parent.treeViewXML.tree_SoftwareVersion_update(full_path[1:], value)
            if tag == "CoordinateSystem":
                self.parent.treeViewXML.tree_CRS_update(full_path[1:], value)
            if tag == "HeightSystem":
                self.parent.treeViewXML.tree_HeightSystem_update(full_path[1:], value)
            if tag == "MeasurementUnit":
                self.parent.treeViewXML.tree_MeasurementUnit_update(full_path[1:], value)
            if tag == "CadastralZoneNumber":
                self.parent.treeViewXML.tree_CadastralZoneNumber_update(full_path[1:], value)
            if tag == "CadastralQuarterNumber":
                self.parent.treeViewXML.tree_CadastralQuarterNumber_update(full_path[1:], value)
            if tag == "ParcelID":
                self.parent.treeViewXML.tree_ParcelID_update(full_path[1:], value)
            if tag == "LocalAuthorityHead":
                self.parent.treeViewXML.tree_LocalAuthorityHead_update(full_path[1:], value)
            if tag == "DKZRHead":
                self.parent.treeViewXML.tree_DKZRHead_update(full_path, value)


            log_msg(logFile, "Пвернення з функції tree_XXXXX_update()")
            # ✅ 2025.01.30 02:02:55 можливо сигнал не потрібний
            # log_msg(logFile, f"емітуємо сигнал dataChangedInTable.emit({full_path}, {value})")
            # self.dataChangedInTable.emit(full_path, value)
        finally:
            self.table_block_change_flag = False
            log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")
            pass


    def on_tree_item_text_changed_metadata(self, full_path, value):
        """ Оновлення таблиці при зміні дерева
            # Викликається з конструктора xml_uaDockWidget 
            # слот для сигналу dataChangedInTree
        """
        log_msg(logFile, "value = {value}")
        log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")
        if self.table_block_change_flag:
            return
        
        self.table_block_change_flag = True
        log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")
        try:
            # for row in range(self.items_model.rowCount()):
            #     key_item = self.items_model.item(row, 0)
            #     if key_item.text() == full_path:
            #         self.items_model.item(row, 1).setData(value, Qt.EditRole)
            #         break
            row = self.get_row_from_path(full_path)
            log_msg(logFile, "row = {row}, value = {value}")
            self.items_model.item(row, 1).setData(value, Qt.EditRole)

        finally:
            self.table_block_change_flag = False
            log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")


    def get_row_from_path(self, full_path: str):
        """ Вертає номер рядка таблиці метаданих
            по повному шляху елемента дерева у форматі без початкового слеша
        """
        log_msg(logFile)
        #log_msg(logFile, f"full_path = {full_path}")
        if full_path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileDate":    return 0
        if full_path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileGUID":   return 1
        if full_path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FormatVersion":     return 2
        if full_path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverName":      return 3
        if full_path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverIdentifier":return 4
        if full_path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/Software":          return 5
        if full_path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/SoftwareVersion":   return 6
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/CoordinateSystem":         return 7
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/HeightSystem":             return 8
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/MeasurementUnit":          return 9
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralZoneNumber":                                                                   return 10
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/CadastralQuarterNumber":                         return 11
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/ParcelID":   return 12
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead":            return 13
        if full_path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead":                      return 14
        return None


    def table_double_click(self, index: QModelIndex):
        """
        Обробляє подвійний клік
        """
        log_msg(logFile)
        if not index.isValid():
            # log_msg(logFile, "Клік поза межами таблиці")
            return

        row = index.row()
        column = index.column()
        value = self.items_model.data(index)  # Отримуємо значення з моделі

        # QMessageBox.warning(None, "Повідомлення", f"Подвійний клік на рядку {row}, колонці {column}, значення: {value}")
        log_msg(logFile, f"{value}")
        log_msg(logFile, f"table 🚩 {self.table_block_change_flag}")


    def table_right_click(self, position):
        """ Обробка події правого кліка таблиці метаданих
        """
        index = self.indexAt(position)  # Отримуємо QModelIndex за позицією
        log_msg(logFile, f"index({index.column()}, {index.row()})")
        if not index.isValid():
            # log_msg(logFile, "Клік поза межами таблиці")
            pass
        if index.column() == 1:
            if index.row() == 0: # FileDate
                # log_msg(logFile, f"FileDate ({index.column()}, {index.row()})")
                menu = QMenu()
                generate_date_action = menu.addAction("Дата формування файлу")
                action = menu.exec_(self.viewport().mapToGlobal(position))
                if action == generate_date_action:
                    # log_msg(logFile, "Вибір пункту контекстного меню Дата формування файлу")
                    self.metadata_set_date_dialog(index)
                else:
                    log_msg(logFile, "Відміна контекстного меню Дата формування файлу")
                    pass
            if index.row() == 1: # FileGUID
                # log_msg(logFile, f"FileGUID ({index.column()}, {index.row()})")
                menu = QMenu()
                generate_guid_action = menu.addAction("Згенерувати GUID")
                action = menu.exec_(self.viewport().mapToGlobal(position))
                if action == generate_guid_action:
                    # Генеруємо GUID
                    new_guid = "{" + str(uuid.uuid4()) + "}"
                    # log_msg(logFile, f"new_guid = {new_guid}")
                    # Оновлюємо значення комірки
                    self.items_model.setData(index, new_guid, Qt.EditRole)
            #  index.row() == 2: Версія формату обмінного файлу - нема контекстного меню
            if index.row() == 3: # TODO написати функцію вибору області і відідлу ДЗК
                menu = QMenu()

                if "Receiver" in config:
                    receiver_section = config["Receiver"]
                    # Додаємо елементи секції в меню
                    actions = {}
                    for key, value in receiver_section.items():
                        actions[menu.addAction(value)] = (key, value)

                    # Показуємо меню і обробляємо вибір
                    action = menu.exec_(self.viewport().mapToGlobal(position))
                    if action:
                        selected_key, selected_value = actions[action]

                        # Записуємо вибране значення у комірку (row = 3, col = 1)
                        value_index = self.items_model.index(3, 1)
                        self.items_model.setData(value_index, selected_value)

                        # Записуємо ключ у комірку (row = 4, col = 1)
                        key_index = self.items_model.index(4, 1)
                        self.items_model.setData(key_index, selected_key)
            if index.row() == 7: # Рядок для системи координат
                # Створюємо контекстне меню
                menu = QMenu()
                coordinate_systems = [
                    "SC42",
                    "SC42_3",
                    "USC2000",
                    "WGS84",
                    "Local",
                    "SC63,X",
                    "SC63,C",
                    "SC63,P",
                    "SC63,T"
                ]
                actions = {menu.addAction(system): system for system in coordinate_systems}
                # Показуємо меню
                action = menu.exec_(self.viewport().mapToGlobal(position))
                if action:
                    selected_system = actions[action]
                    # Якщо обрано Local, запитуємо реєстраційний номер
                    if selected_system == "Local":
                        reg_number, ok = QInputDialog.getText(self, "Реєстраційний номер", "Введіть реєстраційний номер локальної СК:")
                        if ok and reg_number.strip():
                            selected_system = f"Local ({reg_number.strip()})"
                    # log_msg(logFile, f"selected_system = {selected_system}")
                    # Оновлюємо таблицю
                    # log_msg(logFile, f"self.items_model = {self.items_model}")
                    self.items_model.setData(index, selected_system, Qt.EditRole)
            if index.row() == 8: # Рядок для системи висот
                # Створюємо контекстне меню
                menu = QMenu()
                height_systems = ["Baltic", "Baltic77", "Other"]
                actions = {menu.addAction(system): system for system in height_systems}
                # Показуємо меню
                action = menu.exec_(self.viewport().mapToGlobal(position))
                if action:
                    selected_system = actions[action]
                    # Оновлюємо таблицю
                    self.items_model.setData(index, selected_system, Qt.EditRole)
            if index.row() == 9: # Рядок Одиниця виміру довжини
                # Створюємо контекстне меню
                menu = QMenu()
                units = ["M", "Km", "Other"]
                actions = {menu.addAction(system): system for system in units}
                # Показуємо меню
                action = menu.exec_(self.viewport().mapToGlobal(position))
                if action:
                    selected_unit = actions[action]
                    # Оновлюємо таблицю
                    self.items_model.setData(index, selected_unit, Qt.EditRole)
            # index.row() == 10: Номер кадастрової зони - нема контекстного меню
            # index.row() == 11: Номер кадастрового кварталу - нема контекстного меню
            # index.row() == 12: Номер земельної ділянки - нема контекстного меню
            # index.row() == 13: TODO Прізвище, ім’я та по батькові керівника органу виконавчої влади або місцевого самоврядування
            # index.row() == 14: TODO Прізвище, ім’я та по батькові начальника територіального органу земельних ресурсів
            # index.row() == 15: Номер земельної ділянки - нема контекстного меню


    def metadata_set_date_dialog(self, index):
        """ Відкриття діалогу вводу дати
        """
        current_value = index.data(Qt.EditRole)
        log_msg(logFile)
        # log_msg(logFile, f"current_value = {current_value}")

        default_date = QDate.fromString(current_value, "yyyy-MM-dd")
        # log_msg(logFile, f"default_date = {default_date}")

        # if current_value else QDate.currentDate()
        dialog = DateInputDialog(default_date=default_date)
        # log_msg(logFile, f"dialog = {dialog}")

        if dialog.exec_() == QDialog.Accepted:
            # log_msg(logFile, f"dialog.exec_() == QDialog.Accepted")
            # Отримання дати з діалогу та оновлення моделі
            new_date_str = dialog.get_date()
            # log_msg(logFile, f"dialog::new_date_str = {new_date_str}")
            self.items_model.setData(index, new_date_str, Qt.EditRole)
        else:
            log_msg(logFile, f"dialog.exec_() != QDialog.Accepted")
            pass


    def fill_meta_data(self, xmlTree):
        """
            Populates the table with data from the provided XML tree and sets tooltips for the items.
            Args:
                xmlTree (ElementTree): The XML tree containing the data to 
                  be populate the table.
            The function performs the following tasks:
                - Clears the existing table data.
                - Reads configuration paths for metadata.
                - Iterates through the paths and processes specific elements 
                  from the XML tree, such as CoordinateSystem, HeightSystem, 
                  and MeasurementUnit.
                - Adds simple data elements to the table.
                - Extracts and formats the full name of the LocalAuthorityHead 
                  and DKZRHead from the XML tree.
                - Sets tooltips and flags for the table items.
                - Validates the full names and highlights invalid entries.
                - Resizes the first column to fit its contents.
        """
        # log_msg(logFile)
        #self.items_model.blockSignals(True)
        # Очистка таблиці (при повторних відкриттях)
        # log_msg(logFile, f"xmlTree = {xmlTree}")
        self.items_model.removeRows(0, self.items_model.rowCount())
        paths = config.get("Metadata", "paths").splitlines()

        for path in paths:
            element_name = path.split("/")[-1]
            # Винятки комплексних даних
            if path.split("/")[-1] == "CoordinateSystem":
                for element in xmlTree.findall(".//CoordinateSystem"):
                    value = self.read_coordinate_system(element)
                    key_item = QStandardItem("Система координат")
                    full_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/CoordinateSystem"
                    key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Дозволяє лише вибір і активацію
                    key_item.setToolTip(
                        "<b>Оберіть систему координат</b> (правим кліком на значенні)<br>"
                        "Для SC63 район X підходить для більшості території України)<br>"
                        "Для місцевої СК (Local) введіть реєстраційний номер у форматі<br>"
                        "МСК-XX (де XX - цифровий код місцевості")
                    value_item = QStandardItem(value)
                    value_item.setData(path, Qt.UserRole) 
                    if "Local" in value:
                        value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)
                    self.items_model.appendRow([key_item, value_item])
                continue
            if path.split("/")[-1] == "HeightSystem":
                for element in xmlTree.findall(".//HeightSystem"):
                    # Обробляємо систему висот
                    value = self.read_height_system(element)
                    key_item = QStandardItem("Система висот")
                    key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
                    key_item.setToolTip(
                        "<b>Оберіть систему висот</b> (правим кліком на значенні)<br>"
                        "Можливі значення:<br>"
                        "Baltic (Балтійська застаріла)<br>"
                        "Baltic77 (чинна Балтійська уточнена)<br>"
                        "Other інша<br>")
                    value_item = QStandardItem(value)
                    value_item.setData(path, Qt.UserRole) 
                    self.items_model.appendRow([key_item, value_item])
                continue
            if path.split("/")[-1] == "MeasurementUnit":
                #log_msg(logFile, f"path = {path}")
                metric_info = xmlTree.find(".//MetricInfo")
                if metric_info is not None:
                    measurement_unit = metric_info.find("MeasurementUnit")
                    if measurement_unit is not None:
                        child_elements = list(measurement_unit)
                        if child_elements:
                            value = child_elements[0].tag
                        else:
                            value = "Unknown"
                    else:
                        value = "Unknown"
                    key_item = QStandardItem("Одиниця виміру довжини")
                    key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    key_item.setToolTip(
                        "<b>Оберіть одиницю виміру</b><br>"
                        "Можливі значення:<br>"
                        "M (метри)<br>"
                        "Km (кілометри)<br>"
                        "Other (інша)<br>")
                    value_item = QStandardItem(value)
                    value_item.setData(path, Qt.UserRole)
                    value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)
                    self.items_model.appendRow([key_item, value_item])
                else:
                    log_msg(logFile, "MetricInfo not found in XML.")
                    pass
                continue
            # Додавання простих даних
            ukr_description = self.parent.get_tooltip_from_tree(path[1:], path.split("/")[-1])
            key_item = QStandardItem(ukr_description)
            value = xmlTree.xpath(f"{path}")[0].text.strip()
            key_item = QStandardItem(ukr_description)
            value_item = QStandardItem(value if value else "")
            value_item.setData(path, Qt.UserRole)
            key_item.setEditable(False)
            value_item.setEditable(True)
            key_item.setToolTip(self.tooltips.get(path.split("/")[-1], ""))
            self.items_model.appendRow([key_item, value_item])

        last_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/LastName")
        first_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/FirstName")
        middle_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/MiddleName")
        last_name_value = last_name.text.strip() if last_name is not None and last_name.text else ""
        first_name_value = first_name.text.strip() if first_name is not None and first_name.text else ""
        middle_name_value = middle_name.text.strip() if middle_name is not None and middle_name.text else ""
        full_name = f"{last_name_value} {first_name_value} {middle_name_value}".strip()
        key_item = QStandardItem("ПІБ керівника виконавчої влади")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
        key_item.setToolTip(
            "Формат: <Прізвище Ім'я По батькові>\n"
            "Приклад: Іваненко Петро Андрійович\n"
            "MiddleName (По батькові) необов'язковий"
        )
        path = "/UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead"
        value_item = QStandardItem(full_name)
        value_item.setData(path, Qt.UserRole)
        value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)  # Дозволяємо редагування
        # Перевірка на відповідність масці
        if not self.validate_full_name(full_name):
            value_item.setBackground(Qt.red)
        self.items_model.appendRow([key_item, value_item])

        last_name   = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/DKZRHead/LastName")
        first_name  = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/DKZRHead/FirstName")
        middle_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/DKZRHead/MiddleName")
        last_name_value = last_name.text.strip() if last_name is not None and last_name.text else ""
        first_name_value = first_name.text.strip() if first_name is not None and first_name.text else ""
        middle_name_value = middle_name.text.strip() if middle_name is not None and middle_name.text else ""
        full_name = f"{last_name_value} {first_name_value} {middle_name_value}".strip()
        key_item = QStandardItem("ПІБ начальника ТО ЗР")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
        key_item.setToolTip(
            "ПІБ начальника територіального органу земельних ресурсів\n"
            "Формат: <Прізвище Ім'я По батькові>\n"
            "Приклад: Іваненко Петро Андрійович\n"
            "MiddleName (По батькові) необов'язковий"
        )
        path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead"
        value_item = QStandardItem(full_name)
        value_item.setData(path, Qt.UserRole)
        value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)  # Дозволяємо редагування
        # Перевірка на відповідність масці
        if not self.validate_full_name(full_name):
            value_item.setBackground(Qt.red)
        self.items_model.appendRow([key_item, value_item])



        self.resizeColumnToContents(0)


    def validate_full_name(self, full_name):
        """
        Перевіряє ПІБ на відповідність формату.
        """
        # log_msg(logFile, "Кириличні літери, апостроф, крапка")
        import re
        pattern = r"^[А-ЯІЇЄҐ][а-яіїєґ']+ [А-ЯІЇЄҐ][а-яіїєґ'\.]+(?: [А-ЯІЇЄҐ][а-яіїєґ'\.]+)?$"
        return bool(re.match(pattern, full_name))


    def read_coordinate_system(self, xml_element):
        """
        Обробляє систему координат з XML і повертає значення для таблиці.
        """
        # log_msg(logFile)
        if xml_element.tag == "CoordinateSystem":
            # Отримуємо підтеги
            sub_elements = list(xml_element)
            if not sub_elements:
                return "Unknown"

            # Якщо є один підтег Local
            if sub_elements[0].tag == "Local":
                return "Local (редагувати вручну)"

            # Якщо SC63 з зонами
            if sub_elements[0].tag == "SC63":
                zone = list(sub_elements[0])  # Отримуємо дочірні елементи SC63
                if zone:
                    return f"SC63,{zone[0].tag}"

            # Інші випадки
            return sub_elements[0].tag
        return "Unknown"


    def read_height_system(self, xml_element):
        """ """
        # log_msg(logFile, "Обробляє систему висот з XML і повертає значення для таблиці")

        if xml_element.tag == "HeightSystem":
            sub_elements = list(xml_element)
            if not sub_elements:
                return "Unknown"

            # Отримуємо тег першого дочірнього елемента
            tag = sub_elements[0].tag

            # Перевіряємо, чи це варіант із дубльованим тегом (наприклад, <Baltic><Baltic/>)
            if len(sub_elements) > 1 and sub_elements[1].tag == tag:
                return tag

            return tag

        return "Unknown"
