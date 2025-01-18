# -*- coding: utf-8 -*-
"""Обробка XML дерева"""

import re

from lxml import etree

from qgis.PyQt.QtWidgets import QMenu
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QTreeView
from qgis.PyQt.QtWidgets import QAbstractItemView
from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QStandardItemModel
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import pyqtSignal

from .date_dialog import DateInputDialog

from .common import logFile
from .common import log_msg
from .common import log_msg
from .common import config

class CustomTreeView(QTreeView):
    """ Клас віджета XML дерева
    """
    # Signal to synchronize data changes
    dataChangedSignal = pyqtSignal(str, str)

    def __init__(self, parent=None):
        """ Конструктор віджету дерева XML

            Встановлює обробку подій:
                - правого кліка (запит контекстного меню)
                - зміну даних (моделі) дерева

            Параметри:
                parent: вказівник на батьківський віджет
        """
        super().__init__(parent)
        self.parent_widget = parent
        # log_msg(logFile, "self: parent, xml_tree, xsd_descriptions, allowed_dothers")

        self.xml_tree = None
        self.xsd_descriptions = {}

        self.model = QStandardItemModel()
        self.setModel(self.model)
        self.model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSelectionMode(QAbstractItemView.NoSelection)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.allowed_dothers = {}
        self.load_allowed_dothers()

        self.elements_to_expand = config.get("ElementsToExpand", "expanded").split(", ")
        # log_msg(logFile, f"self.elements_to_expand = {self.elements_to_expand}")

        self.model.itemChanged.connect(self.on_tree_model_data_changed)
    def load_allowed_dothers(self):
        """ Завантаження списків дозволених дочірніх елементів

            Списки дозволених дочірніх елементів описуються в ini.
            Оскільки, не всім елементам дерева можна додавати дочірні.

        """
        # log_msg(logFile, "Завантажуємо allowed_dothers з INI")

        # self.allowed_dothers = {}

        # Завантажуємо секцію [AllowedDothers]
        if "AllowedDothers" in config:
            for path, rules in config["AllowedDothers"].items():
                self.allowed_dothers[path.strip()] = {}
                # Видаляємо зайві пробіли
                rules = " ".join(rules.split())
                elements = rules.split(" ")
                for i in range(0, len(elements), 2):
                    try:
                        element = elements[i]
                        limit = int(elements[i + 1])  # Перетворюємо кількість на число
                        self.allowed_dothers[path.strip()][element] = limit
                    except (IndexError, ValueError):
                        log_msg(logFile, f"Помилка у секції [AllowedDothers] для шляху '{path.strip()}': {rules}")  # pylint: disable=line-too-long
    def show_context_menu(self, position):
        """ 
        
        """
        index = self.indexAt(position)
        log_msg(logFile, f"row {index.row()}, col {index.column()}")
        if not index.isValid():
            return

        item = self.model.itemFromIndex(index)  # Поточний елемент дерева
        path = self.get_element_path(item)  # Формуємо повний шлях до елемента

        menu = QMenu()

        # Дія "Додати дочірній елемент"
        if path in self.allowed_dothers:
            add_child_menu = QMenu("Додати дочірній елемент", menu)

            for child_name, max_count in self.allowed_dothers[path].items():
                child_count = self.get_current_child_count(item, child_name)

                # Дозволяємо додати елемент, якщо обмеження не досягнуто
                if max_count == 0 or child_count < max_count:
                    child_action = QAction(child_name, menu)
                    child_action.triggered.connect(self.create_add_child_callback(item, child_name))
                    add_child_menu.addAction(child_action)

            if add_child_menu.actions():
                menu.addMenu(add_child_menu)

        # Відображення контекстного меню
        menu.exec_(self.viewport().mapToGlobal(position))
    def get_element_path(self, item):
        """
        Побудова повного шляху до елемента дерева.
        """
        log_msg(logFile)
        path = []
        while item:
            path.insert(0, item.text())
            item = item.parent()

        return "/" + "/".join(path)
    def get_current_child_count(self, parent_item, child_name):
        """
        Підраховує кількість дочірніх елементів із зазначеним іменем.
        """
        log_msg(logFile)
        count = 0
        for i in range(parent_item.rowCount()):
            if parent_item.child(i).text() == child_name:
                count += 1
        return count
    def create_add_child_callback(self, parent_item, child_name):
        """
        Створює замикання для додавання дочірнього елемента.
        """
        log_msg(logFile)
        return lambda: self.add_child(parent_item, child_name)
    def add_child(self, item, child_name):
        """
        Додає дочірній елемент до вказаного елемента дерева.
        """
        log_msg(logFile)
        child_item = QStandardItem(child_name)
        child_item.setEditable(False)  # Забороняємо редагування назви елемента
        item.appendRow([child_item, QStandardItem("")])
    def create_tree_item(self, xml_element, parent_path):
        """Рекурсивне створення дерева."""
        log_msg(logFile)
        full_path = f"{parent_path}/{xml_element.tag}" if parent_path else xml_element.tag
        ukr_name = self.ukr_descriptions.get(full_path, xml_element.tag)

        item = QStandardItem(ukr_name)
        item.setEditable(False)

        value = QStandardItem(xml_element.text.strip() if xml_element.text else "")
        value.setEditable(True)

        for child in xml_element:
            child_item = self.create_tree_item(child, full_path)
            item.appendRow(child_item)

        return [item, value]
    def change_value(self):
        """
        Змінює значення вибраного елемента.
        """
        log_msg(logFile)
        index = self.currentIndex()
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        if item:
            # Наприклад, встановлюємо нове значення (можна реалізувати через діалог)
            new_value = "Новe Значення"  # Український текст
            item.setText(new_value)
            item.setToolTip("Оновлене значення елемента")  # Український опис
    def validate_value(self, item):
        """Перевіряє валідність числового значення."""
        log_msg(logFile)
        if item.text().isdigit():
            QMessageBox.information(self, "Валідність", "Значення є валідним числом.")
        else:
            QMessageBox.warning(self, "Валідність", "Значення не є валідним числом!")
    def add_child_item(self):
        """
        Додає дочірній елемент до вибраного елемента.
        """
        log_msg(logFile)
        index = self.currentIndex()
        if not index.isValid():
            return
        parent_item = self.model.itemFromIndex(index)
        if parent_item:
            child_name = "Новий елемент"
            child_item = QStandardItem(child_name)
            child_item.setToolTip("Опис нового елемента")  # Український опис
            parent_item.appendRow([child_item, QStandardItem("")])
        return
    def delete_item(self):
        """
        Видаляє вибраний елемент.
        """
        log_msg(logFile)
        index = self.currentIndex()
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        if item:
            parent = item.parent()
            if parent:
                parent.removeRow(item.row())
            else:
                self.model.removeRow(item.row())
        return
    def on_tree_model_data_changed(self, item):
        """
        Обробка зміни елемента в TreeView.
        Це також оновлює відповідне значення в таблиці.
        """
        log_msg(logFile)
        if item.column() == 1:  # Оновлюємо тільки значення
            # Отримує шлях до зміненого елемента в дереві через метод get_item_path
            path = self.get_item_path(item)
            value = item.text()

            # log_msg(logFile, f"item path = {path}")
            # log_msg(logFile, f"item value = {value}")

            # Емітує сигнал dataChangedSignal для синхронізації змін із таблицею
            self.dataChangedSignal.emit(path, value)

            # Синхронізація із таблицею
            metadata_model = self.parent_widget.tableViewMetadata.model

            if metadata_model:
                for row in range(metadata_model.rowCount()):
                    key_item = metadata_model.item(row, 0)
                    if key_item and key_item.data(Qt.UserRole) == path:
                        value_item = metadata_model.item(row, 1)
                        value_item.setText(value)

                        # Перевірка маски cadastral_zone
                        if row == 10:
                            if self.validate_cad_zone_number(value):
                                value_item.setBackground(Qt.white)
                            else:
                                # log_msg(logFile, f"{value}: Встановлюємо червоний колір тла")
                                value_item.setBackground(Qt.red)
                            break

                        # Перевірка маски quarter
                        if row == 11:
                            if self.validate_cad_quarter_number(value):
                                value_item.setBackground(Qt.white)
                            else:
                                # log_msg(logFile, f"{value}: Встановлюємо червоний колір тла")
                                value_item.setBackground(Qt.red)
                            break

                        # Отримання значень всіх частин ПІБ
                        last_name = self.get_element_text("UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/LastName")  # pylint: disable=line-too-long
                        first_name = self.get_element_text("UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/FirstName")  # pylint: disable=line-too-long
                        middle_name = self.get_element_text("UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/MiddleName")  # pylint: disable=line-too-long

                        # Формування нового значення ПІБ
                        full_name = f"{last_name} {first_name} {middle_name}".strip()

                        # Оновлення таблиці
                        metadata_model = self.tableViewMetadata.model()
                        for row in range(metadata_model.rowCount()):
                            key_item = metadata_model.item(row, 0)
                            if key_item and key_item.data(Qt.UserRole) == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead":  # pylint: disable=line-too-long
                                value_item = metadata_model.item(row, 1)
                                value_item.setText(full_name)

                                # Валідація
                                if self.validate_full_name(full_name):
                                    value_item.setBackground(Qt.white)
                                else:
                                    value_item.setBackground(Qt.red)
                                break

            # Емітує сигнал dataChangedSignal для синхронізації змін із таблицею
            self.dataChangedSignal.emit(path, value)
    def expand_initial_elements(self):
        """ Розкриває задані елементи дерева після завантаження XML.

            Список елементів, які повинні бути розкриті після 
            завантаження elements_to_expand описується в ini.

        """
        log_msg(logFile, "")

        # Отримання моделі дерева
        model = self.model
        if model is None:
            return

        def expand_recursively(index):
            """
            Рекурсивно розкриває вузли дерева, якщо їхній тег у списку self.elements_to_expand.

            :param index: Індекс поточного елемента в моделі.
            """
            item = model.itemFromIndex(index)
            if item is None:
                return

            # Перевірка, чи потрібно розкрити елемент
            if item.text() in self.elements_to_expand:
                self.expand(index)

            # Обхід дочірніх елементів
            for row in range(item.rowCount()):
                child_index = model.index(row, 0, index)
                expand_recursively(child_index)

        # Початковий вузол
        root_index = model.index(0, 0)
        expand_recursively(root_index)

        return
    def get_item_path(self, item):
        """
        Отримує шлях до елемента в TreeView.
        """
        log_msg(logFile)
        path = []
        while item:
            # Отримуємо текст із першої колонки
            parent = item.parent()
            if parent:
                key = parent.child(item.row(), 0).text()  # Беремо текст із колонки 0
            else:
                key = self.model.item(item.row(), 0).text()  # Якщо елемент кореневий
            path.insert(0, key)
            item = parent
        return "/".join(path)
    def set_column_width(self, column_index, width_percentage):
        """
            Встановлює ширину колонки у відсотках від ширини CustomTreeView.

            :param self: Віджет типу CustomTreeView.
            :param column_index: Індекс колонки для зміни ширини.
            :param width_percentage: Ширина колонки у відсотках від загальної ширини TreeView (0-100).
        """
        log_msg(logFile, "Встановлює ширину колонки")
        total_width = self.viewport().width()
        column_width = int(total_width * width_percentage / 100)
        self.setColumnWidth(column_index, column_width)
    def validate_cad_zone_number(self, value):
        """ Перевіряє значення на відповідність масці "9999999999:99".
        """
        log_msg(logFile)

        pattern = r"^\d{10}:\d{2}$"
        return bool(re.match(pattern, value))
    def validate_cad_quarter_number(self, value):
        """ Перевіряє значення на відповідність масці "999".
        """
        log_msg(logFile)
        # import re
        pattern = r"^\d{3}$"
        # log_msg(logFile, f"bool(re.match(pattern, {value})) = {bool(re.match(pattern, value))}")

        return bool(re.match(pattern, value))
    def validate_full_name(self, full_name):
        """
        Перевіряє ПІБ на відповідність формату:
        - Прізвище, Ім'я та (за потреби) По батькові
            мають містити тільки літери українського алфавіту.
        - У Ім'я та По батькові допускаються крапки.
        """
        log_msg(logFile)
        pattern = r"^[А-ЯІЇЄҐ][а-яіїєґ']+ [А-ЯІЇЄҐ][а-яіїєґ'\.]+(?: [А-ЯІЇЄҐ][а-яіїєґ'\.]+)?$"
        return bool(re.match(pattern, full_name))
    def update_coordinate_system_tree(self, path, value):
        """
        Оновлює дерево для значення "Система координат" відповідно до XSD.
        """
        log_msg(logFile)
        coordinate_system_index = self.find_element_index(path)  # pylint: disable=line-too-long
        if not coordinate_system_index.isValid():
            log_msg(logFile, "Елемент CoordinateSystem не знайдено у дереві.")
            return

        # Видаляємо попередній вміст CoordinateSystem
        coordinate_system_item = self.model.itemFromIndex(coordinate_system_index)
        coordinate_system_item.removeRows(0, coordinate_system_item.rowCount())

        # Створюємо новий вміст залежно від значення
        if value.startswith("Local ("):
            # Місцева система координат
            local_name = value[value.find("(") + 1:value.find(")")]  # Отримуємо текст у дужках
            local_item = QStandardItem("Local")
            local_value_item = QStandardItem(local_name)
            coordinate_system_item.appendRow([local_item, local_value_item])
        elif value.startswith("SC63,"):
            # SC63 із додатковими параметрами
            sc63_item = QStandardItem("SC63")
            coordinate_system_item.appendRow([sc63_item, QStandardItem()])

            # Додаємо дочірній елемент для SC63
            additional_value = value.split(",")[1].strip()  # Отримуємо значення після коми
            # additional_item = QStandardItem(additional_value)
            sc63_item.appendRow([QStandardItem(additional_value), QStandardItem()])
        else:
            # Інші значення: SC42, SC42_3, UCS2000, WGS84
            simple_item = QStandardItem(value)
            simple_value_item = QStandardItem("")
            coordinate_system_item.appendRow([simple_item, simple_value_item])

        # log_msg(logFile, f"Оновлено CoordinateSystem: {value}")
        return
    def update_height_system_tree(self, value):
        """
        Оновлює дерево для значення "Система висот" відповідно до XSD.
        """
        log_msg(logFile)
        height_system_index = self.find_element_index(path="UkrainianCadastralExchangeFile/InfoPart/MetricInfo/HeightSystem")  # pylint: disable=line-too-long
        if not height_system_index.isValid():
            # log_msg(logFile, "Елемент HeightSystem не знайдено у дереві.")
            return

        # Видаляємо старий піделемент
        height_system_item = self.model.itemFromIndex(height_system_index)
        height_system_item.removeRows(0, height_system_item.rowCount())

        # Додаємо новий піделемент
        new_item = QStandardItem(value)
        if value == "Other":
            # Якщо вибрано "Other", додаємо піделемент без опису
            height_system_item.appendRow([new_item, QStandardItem()])
        else:
            # Для інших значень додаємо піделемент із текстом (значенням) у дочірньому вузлі
            height_system_item.appendRow([new_item, QStandardItem("")])

        # log_msg(logFile, f"Оновлено HeightSystem: {value}")

        return
    def update_measurement_unit_tree(self, value):
        """
        Оновлює дерево для значення "Одиниця виміру довжини" відповідно до XSD.
        """
        log_msg(logFile, f"value = {value}")
        measurement_unit_index = self.find_element_index(path="UkrainianCadastralExchangeFile/InfoPart/MetricInfo/MeasurementUnit")  # pylint: disable=line-too-long
        if not measurement_unit_index.isValid():
            log_msg(logFile, "Елемент MeasurementUnit не знайдено у дереві.")
            return

        # Видаляємо старий піделемент
        measurement_unit_item = self.model.itemFromIndex(measurement_unit_index)
        measurement_unit_item.removeRows(0, measurement_unit_item.rowCount())

        # Додаємо новий піделемент
        new_item = QStandardItem(value)
        measurement_unit_item.appendRow([new_item, QStandardItem()])

        log_msg(logFile, f"Оновлено MeasurementUnit: {value}")
    def update_cadastral_zone_number_tree(self, value):
        """
        Оновлює дерево для значення "Номер кадастрової зони".
        """
        log_msg(logFile)
        cadastral_zone_number_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralZoneNumber"
        )
        if not cadastral_zone_number_index.isValid():
            log_msg(logFile, "Елемент CadastralZoneNumber не знайдено у дереві.")
            return

        # Оновлюємо значення у другій колонці вузла
        cadastral_zone_number_item = self.model.itemFromIndex(cadastral_zone_number_index)
        if cadastral_zone_number_item:
            # old_value = cadastral_zone_number_item.parent().child(
                # cadastral_zone_number_item.row(), 1
            # ).text()  # Старе значення
            # log_msg(logFile, f"Old value in tree: {old_value}")

            # Оновлюємо текст у другій колонці
            cadastral_zone_number_item.parent().child(
                cadastral_zone_number_item.row(), 1
            ).setText(value)
            # new_value = cadastral_zone_number_item.parent().child(
                # cadastral_zone_number_item.row(), 1
            # ).text()  # Нове значення
            # log_msg(logFile, f"New value in tree: {new_value}")

        return
    def update_cadastral_quarter_tree(self, value):
        """
        Оновлює дерево для значення "Номер кадастрового кварталу".
        """
        log_msg(logFile)
        cadastral_quarter_number_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/CadastralQuarterNumber"  # pylint: disable=line-too-long
        )
        if not cadastral_quarter_number_index.isValid():
            log_msg(logFile, "Елемент CadastralQuarterNumber не знайдено у дереві.")
            return

        # Оновлюємо значення у другій колонці вузла
        cadastral_quarter_number_item = self.model.itemFromIndex(cadastral_quarter_number_index)
        if cadastral_quarter_number_item:
            # old_value = cadastral_quarter_number_item.parent().child(
                # cadastral_quarter_number_item.row(), 1
            # ).text()  # Старе значення
            # log_msg(logFile, f"Old value in tree: {old_value}")

            # Оновлюємо текст у другій колонці
            cadastral_quarter_number_item.parent().child(
                cadastral_quarter_number_item.row(), 1
            ).setText(value)
            # new_value = cadastral_quarter_number_item.parent().child(
                # cadastral_quarter_number_item.row(), 1
            # ).text()  # Нове значення
            # log_msg(logFile, f"New value in tree: {new_value}")
        return
    def update_file_date_tree(self, path, value):
        """ Оновлення дерева при зміні FileDate
        """
        log_msg(logFile, "Оновлення дерева при зміні FileDate")
        file_date_index = self.find_element_index(path)
        if not file_date_index.isValid():
            log_msg(logFile, "Елемент FileDate не знайдено у дереві.")
            return
        file_date_item = self.model.itemFromIndex(file_date_index)
        file_date_item.parent().child(file_date_item.row(), 1).setText(value)
        return
    def update_file_GUID_tree(self, path, value):
        """ Оновлення дерева при зміні GUID
        """
        log_msg(logFile, "Оновлення дерева при зміні GUID")
        file_GUID_index = self.find_element_index(path)
        if not file_GUID_index.isValid():
            log_msg(logFile, "Елемент GUID не знайдено у дереві.")
            return
        file_GUID_item = self.model.itemFromIndex(file_GUID_index)
        file_GUID_item.parent().child(file_GUID_item.row(), 1).setText(value)
    def update_FormatVersion_tree(self, path, value):
        """ Оновлення дерева при зміні Версія формату обмінного файлу
        """
        log_msg(logFile, "Оновлення дерева при зміні Версія формату обмінного файлу")
        FormatVersion_index = self.find_element_index(path)
        if not FormatVersion_index.isValid():
            log_msg(logFile, "Елемент Версія формату обмінного файлу не знайдено у дереві.")
            return
        FormatVersion_item = self.model.itemFromIndex(FormatVersion_index)
        FormatVersion_item.parent().child(FormatVersion_item.row(), 1).setText(value)
    def update_ReceiverName_tree(self, path, value):
        """ Оновлення дерева при зміні Найменування підрозділу Центру ДЗК
        """
        log_msg(logFile, "Оновлення дерева при зміні Найменування підрозділу Центру ДЗК")
        ReceiverName_index = self.find_element_index(path)
        if not ReceiverName_index.isValid():
            log_msg(logFile, "Елемент Найменування підрозділу Центру ДЗК не знайдено у дереві.")
            return
        ReceiverName_item = self.model.itemFromIndex(ReceiverName_index)
        ReceiverName_item.parent().child(ReceiverName_item.row(), 1).setText(value)
    def update_ReceiverIdentifier_tree(self, path, value):
        """ Оновлення дерева при зміні Ідентифікатор підрозділу Центру ДЗК
        """
        log_msg(logFile, "Оновлення дерева при зміні Ідентифікатор підрозділу Центру ДЗК")
        ReceiverIdentifier_index = self.find_element_index(path)
        if not ReceiverIdentifier_index.isValid():
            log_msg(logFile, "Елемент Ідентифікатор підрозділу Центру ДЗК не знайдено у дереві.")
            return
        ReceiverIdentifier_item = self.model.itemFromIndex(ReceiverIdentifier_index)
        ReceiverIdentifier_item.parent().child(ReceiverIdentifier_item.row(), 1).setText(value)
    def update_Software_tree(self, path, value):
        """ Оновлення дерева при зміні Назва програмного забезпечення
        """
        log_msg(logFile, "Оновлення дерева при зміні Назва програмного забезпечення")
        Software_index = self.find_element_index(path)
        if not Software_index.isValid():
            log_msg(logFile, "Елемент Назва програмного забезпечення не знайдено у дереві.")
            return
        Software_item = self.model.itemFromIndex(Software_index)
        Software_item.parent().child(Software_item.row(), 1).setText(value)
    def update_SoftwareVersion_tree(self, path, value):
        """ Оновлення дерева при зміні Версія програмного забезпечення
        """
        log_msg(logFile, "Оновлення дерева при зміні Версія програмного забезпечення")
        SoftwareVersion_index = self.find_element_index(path)
        if not SoftwareVersion_index.isValid():
            log_msg(logFile, "Елемент Версія програмного забезпечення не знайдено у дереві.")
            return
        SoftwareVersion_item = self.model.itemFromIndex(SoftwareVersion_index)
        SoftwareVersion_item.parent().child(SoftwareVersion_item.row(), 1).setText(value)
    def update_local_authority_head_tree(self, full_name):
        """ Оновлює елементи дерева для значення "ПІБ керівника виконавчої влади".
        """
        log_msg(logFile)
        # Розділення ПІБ
        parts = full_name.split()
        last_name = parts[0] if len(parts) > 0 else ""
        first_name = parts[1] if len(parts) > 1 else ""
        middle_name = parts[2] if len(parts) > 2 else ""

        # Оновлення LastName
        last_name_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/LastName"  # pylint: disable=line-too-long
        )
        if last_name_index.isValid():
            parent_item = self.model.itemFromIndex(last_name_index.parent())
            if parent_item:
                parent_item.child(last_name_index.row(), 1).setText(last_name)  # pylint: disable=line-too-long

        # Оновлення FirstName
        first_name_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/FirstName"  # pylint: disable=line-too-long
        )
        if first_name_index.isValid():
            parent_item = self.model.itemFromIndex(first_name_index.parent())
            if parent_item:
                parent_item.child(first_name_index.row(), 1).setText(first_name)  # pylint: disable=line-too-long

        # Оновлення MiddleName
        middle_name_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/MiddleName"  # pylint: disable=line-too-long
        )
        if middle_name_index.isValid():
            parent_item = self.model.itemFromIndex(middle_name_index.parent())
            if parent_item:
                parent_item.child(middle_name_index.row(), 1).setText(middle_name)  # pylint: disable=line-too-long
    def update_DKZRHead_tree(self, full_name):
        """ Оновлює елементи дерева для значення "ПІБ керівника ТО ЗР".
        """
        log_msg(logFile)
        # Розділення ПІБ
        parts = full_name.split()
        last_name = parts[0] if len(parts) > 0 else ""
        first_name = parts[1] if len(parts) > 1 else ""
        middle_name = parts[2] if len(parts) > 2 else ""

        # Оновлення LastName
        last_name_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/LastName"
        )
        if last_name_index.isValid():
            parent_item = self.model.itemFromIndex(last_name_index.parent())
            if parent_item:
                parent_item.child(last_name_index.row(), 1).setText(last_name)  # pylint: disable=line-too-long

        # Оновлення FirstName
        first_name_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/FirstName"
        )
        if first_name_index.isValid():
            parent_item = self.model.itemFromIndex(first_name_index.parent())
            if parent_item:
                parent_item.child(first_name_index.row(), 1).setText(first_name)  # pylint: disable=line-too-long

        # Оновлення MiddleName
        middle_name_index = self.find_element_index(
            path="UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/MiddleName"
        )
        if middle_name_index.isValid():
            parent_item = self.model.itemFromIndex(middle_name_index.parent())
            if parent_item:
                parent_item.child(middle_name_index.row(), 1).setText(middle_name)
    def read_measurement_unit(self, xml_element):
        """
        Обробляє одиницю виміру довжини з XML і повертає значення для таблиці.
        """
        log_msg(logFile)
        if xml_element.tag == "MeasurementUnit":
            sub_elements = list(xml_element)
            # log_msg(logFile, f"sub_elements = {sub_elements}")
            if not sub_elements:
                return "Unknown"

            # Отримуємо тег першого дочірнього елемента
            tag = sub_elements[0].tag

            # Перевіряємо, чи це варіант із дубльованим тегом (наприклад, <Baltic><Baltic/>)
            if len(sub_elements) > 1 and sub_elements[1].tag == tag:
                # log_msg(logFile, f"варіант із дубльованим тегом tag = {tag}")
                # log_msg(logFile, f"варіант із дубльованим тегом len(sub_elements) = {len(sub_elements)}")  # pylint: disable=line-too-long
                return tag

            # log_msg(logFile, f"tag = {tag}")
            return tag

        return "Unknown"
    def update_tree_view_xml(self, new_element_name, new_value):            # Зміна дерева
        """
        Оновлює відповідний вузол у дереві treeViewXML.
        """
        log_msg(logFile)
        index = self.find_element_index(element_name=new_element_name)
        if index.isValid():
            tree_item = self.model.itemFromIndex(index)
            if tree_item:
                # Оновлюємо текст у вузлі дерева
                tree_item.setText(new_value)
                # log_msg(logFile, f"Оновлено значення у дереві для {new_element_name}: {new_value}")  # pylint: disable=line-too-long
    def get_element_with_namespace(self, element_name, schema):  # pylint: disable=redefined-outer-name
        """ """
        log_msg(logFile)
        for key in schema.elements:
            if key.endswith(element_name):  # Перевірка на збіг імені без урахування простору імен
                return schema.elements[key]
        raise KeyError(f"Елемент '{element_name}' не знайдено у схемі.")
    def find_local_element(self, element_name, schema_xsd):
        """
        Рекурсивно знаходить локальний елемент за його ім'ям у XSD-схемі.
        """
        # log_msg(logFile)
        for elem in schema_xsd.iter():
            if getattr(elem, "name", None) == element_name:  # Перевіряємо ім'я елемента
                return elem
        raise KeyError(f"Елемент '{element_name}' не знайдено у схемі.")
    def get_element_properties(self, element_name, schema_xsd):
        """
        Отримує властивості елемента за його ім'ям у XSD-схемі.
        """
        log_msg(logFile)
        for element in schema_xsd.iter():
            if getattr(element, "name", None) == element_name:
                # Перевіряємо, чи тип має content (тобто не є атомарним)
                if hasattr(element.type, "content") and element.type.content:
                    children = [child.name for child in element.type.content if child.name]
                else:
                    children = []  # Елемент не має дочірніх вузлів
                return {
                    "nillable": element.nillable,
                    "minOccurs": element.min_occurs,
                    "maxOccurs": element.max_occurs,
                    "children": children,
                }
        raise KeyError(f"Елемент '{element_name}' не знайдено у схемі.")
    def extract_descriptions(self, element, full_path="", ns=None, is_root=False):
        """
        Рекурсивно витягує описи з XSD для елементів, включаючи вкладені структури.
        """
        name = element.get("name")
        ref = element.get("ref")

        if ref:
            # Якщо використовується ref, знайти елемент за ref
            ref_element = element.getroottree().xpath(f"//xsd:element[@name='{ref}']", namespaces=ns)  # pylint: disable=line-too-long
            if ref_element:
                self.extract_descriptions(ref_element[0], full_path, ns, is_root=False)
            else:
                print(f"Reference '{ref}' not found in XSD.")
            return

        if name:
            # Формуємо повний шлях
            full_path = f"{full_path}/{name}".strip("/") if full_path else name

            # Витягуємо документацію
            documentation = element.xpath('./xsd:annotation/xsd:documentation', namespaces=ns)
            if documentation:
                self.xsd_descriptions[full_path] = documentation[0].text.strip()

            # Логування для перевірки
            print(f"Extracted: name = '{name}', path = '{full_path}'")

        # Обробка вкладених структур у xsd:complexType
        complex_type = element.xpath('./xsd:complexType', namespaces=ns)
        if complex_type:
            for child in complex_type[0].xpath('./xsd:sequence/xsd:element | ./xsd:choice/xsd:element | ./xsd:all/xsd:element', namespaces=ns):  # pylint: disable=line-too-long
                self.extract_descriptions(child, full_path, ns)

        # Якщо елемент має атрибут type, обробляємо цей тип
        ref_type = element.get("type")
        if ref_type:
            if ref_type.startswith("xsd:"):
                # Пропускаємо вбудовані типи (наприклад, xsd:string)
                pass
            else:
                # Обробка типу (complexType або simpleType)
                ref_element = element.getroottree().xpath(f"//xsd:complexType[@name='{ref_type}'] | //xsd:simpleType[@name='{ref_type}']", namespaces=ns)  # pylint: disable=line-too-long
                if ref_element:
                    print(f"Processing type reference '{ref_type}' for element '{name}'")
                    for ref_child in ref_element[0].xpath('./xsd:sequence/xsd:element | ./xsd:choice/xsd:element | ./xsd:all/xsd:element', namespaces=ns):  # pylint: disable=line-too-long
                        self.extract_descriptions(ref_child, full_path, ns)
    def load_xsd_descriptions(self, path_to_xsd: str):
        """
        Парсує XSD-файл і витягує описи для елементів.
        Формує словник, де ключ — повний шлях до елемента, значення — опис.
        """
        # log_msg(logFile, "Повертає словник описів з XSD")

        self.xsd_descriptions = {}
        try:
            # Парсинг XSD
            xsd_tree = etree.parse(path_to_xsd)  # pylint: disable=c-extension-no-member
            root = xsd_tree.getroot()
            ns = {'xsd': 'http://www.w3.org/2001/XMLSchema'}  # Простір імен для xsd

            # Знаходимо кореневий елемент
            root_element = root.xpath("//xsd:element[@name='UkrainianCadastralExchangeFile']", namespaces=ns)  # pylint: disable=line-too-long
            if root_element:
                self.extract_descriptions(root_element[0], "", ns, is_root=True)
            else:
                log_msg(logFile, "Кореневий елемент 'UkrainianCadastralExchangeFile' не знайдено.")  # pylint: disable=line-too-long
        except Exception as e:
            log_msg(logFile, f"Помилка при парсингу XSD: {e}")  # pylint: disable=broad-except

        # log_dict(logFile, self.xsd_descriptions, msg="xsd_descriptions")
        return self.xsd_descriptions
    def _add_element_to_tree(self, element, parent_item, full_path=""):
        """
        Рекурсивно додає XML-елементи до моделі дерева, встановлюючи підказки.
        """
        # Отримуємо локальне ім'я елемента
        name = etree.QName(element).localname  # pylint: disable=c-extension-no-member

        # Оновлюємо повний шлях
        if full_path:
            full_path = f"{full_path}/{name}"
        else:
            full_path = name

        # log_msg(logFile, f"Adding element: {name}, full_path: {full_path}")

        # Створюємо елементи для моделі
        name_item = QStandardItem(name)
        value_item = QStandardItem(element.text.strip() if element.text else "")

        # Встановлюємо підказку, якщо опис доступний
        description = self.xsd_descriptions.get(full_path, "")
        if description:
            name_item.setToolTip(description)
            value_item.setToolTip(description)

        # Забороняємо редагування ключа (назви)
        name_item.setEditable(False)

        # Додаємо елементи до дерева
        parent_item.appendRow([name_item, value_item])

        # Рекурсивно додаємо дочірні елементи
        for child in element:
            self._add_element_to_tree(child, name_item, full_path)
    def load_xml_to_tree_view(self, xml_path: str, path_to_xsd: str):
        """ """
        # log_msg(logFile, msg="Завантаження XML, описи з XSD")
        try:
            self.xsd_descriptions = self.load_xsd_descriptions(path_to_xsd)

            # Парсимо XML
            self.xml_tree = etree.parse(xml_path)  # pylint: disable=c-extension-no-member

            # log_msg(logFile, msg="Очищаємо існуючу модель дерева")
            self.model.removeRows(0, self.model.rowCount())

            # Додаємо елементи в дерево
            root = self.xml_tree.getroot()
            # log_msg(logFile, msg="Викликаємо рекурсію _add_element_to_tree()")
            self._add_element_to_tree(root, self.model.invisibleRootItem())

        except Exception as e:
            log_msg(logFile, f"Помилка при завантаженні XML: {e}")
    def find_element_index(self, path=None, element_name=None):
        """
        Знаходить індекс елемента у дереві на основі шляху або імені.
        """
        # log_msg(logFile) # recursion
        if path:
            # Логіка пошуку за шляхом
            current_index = QModelIndex()
            path_parts = path.split("/")  # Розділяємо шлях на частини
            for part in path_parts:
                found = False
                for row in range(self.model.rowCount(current_index)):
                    child_index = self.model.index(row, 0, current_index)
                    child_item = self.model.itemFromIndex(child_index)
                    if child_item and child_item.text() == part:
                        # Переходимо на наступний рівень дерева
                        current_index = child_index
                        found = True
                        break
                if not found:
                    # Якщо будь-яка частина шляху не знайдена, повертаємо пустий індекс
                    return QModelIndex()
            return current_index
        elif element_name:
            # Логіка пошуку за іменем
            for row in range(self.model.rowCount()):
                item = self.model.item(row, 0)  # Припустимо, імена у першій колонці
                if item and item.text() == element_name:
                    return self.model.indexFromItem(item)

        return QModelIndex()
