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

from .common import logFile
from .common import log_msg
from .common import log_calls
from .common import config
from .common import connector


class CustomTreeView(QTreeView):

    """ 
        Клас віджета XML дерева
    """

    # Сигнал для повідомлення про зміну даних у вузлі дерева
    # перший параметр full_path
    # другий параметр value
    # шлях (гілки?) і значення (листка?)

    # Коли користувач редагує значення в дереві, викликається метод 
    # on_tree_model_data_changed класу CustomTreeView.
    # Цей метод правильно визначає повний шлях (full_path) до 
    # зміненого елемента та його нове значення (value).
    # Він також правильно емітує сигнал dataChangedInTree, 
    # який може бути використаний для синхронізації з іншими віджетами.
    # Але він не зберігає зміни в XML-дереві (self.xml_tree) 
    # та не викликає функцію збереження на диск.


    dataChangedInTree = pyqtSignal(str, str)

    def __init__(self, parent=None):  # after icon click
        """# ✔ 2025.02.19 09:11:07
        Initializes the CustomTreeView class.
        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        Attributes:
            parent (QWidget): The parent widget.
            tree_upd (bool): Flag to prevent cyclic changes.
            xml_tree (object): The XML tree structure.
            xsd_descriptions (dict): Dictionary to store XSD descriptions.
            tree_row (int): The current row in the tree.
            model (QStandardItemModel): The model for the tree view.
            group_name (str): The name of the group.
            allowed_dothers (dict): Dictionary to store allowed others.
            elements_to_expand (list): List of elements to expand.
        """
        super().__init__(parent)

        # log_msg(logFile, "CustomTreeView")

        self.parent = parent
        self.tree_upd = False   # Флаг для запобігання циклічним змінам
        self.xml_tree = None
        self.xsd_descriptions = {}

        self.tree_row = 0

        self.model = QStandardItemModel()
        self.setModel(self.model)

        self.model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        #self.model.itemChanged.connect(self.on_tree_model_data_changed)
        connector.connect(self.model, "itemChanged", self.on_tree_model_data_changed)
        self.group_name = ""

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        #self.customContextMenuRequested.connect(self.show_context_menu)
        connector.connect(self, "customContextMenuRequested", self.show_context_menu)
        self.allowed_dothers = {}
        self.load_allowed_dothers()
        self.elements_to_expand = config.get(
            "ElementsToExpand", "expanded").split(", ")


    def on_tree_model_data_changed(self, item):
        """ 
            Обробка змін у вузлі дерева, запобігання циклічному виклику 
        """

        # 1.Оновлення self.xml_tree:
        #
        # У методі on_tree_model_data_changed класу CustomTreeView 
        # потрібно додати код, який буде оновлювати відповідний 
        # елемент в self.xml_tree на основі full_path та value.
        # Для цього потрібно:
        #   Розпарсити full_path для знаходження відповідного 
        #   елемента в self.xml_tree.
        #   Оновити text цього елемента на value.
        # 
        # 🔨.Збереження при закритті (опціонально):
        # 
        # Додати обробник події закриття док-віджета (closeEvent) 
        # або плагіна (onClosePlugin), який буде запитувати користувача, 
        # чи потрібно зберегти зміни, якщо вони були.
        

        log_msg(logFile, f"{item.text()}")

        # Якщо вже йде оновлення, нічого не робимо
        if self.tree_upd:  
            log_msg(logFile, "пропускаємо оновлення дерева")
            return

        # Початок синхронізації
        self.tree_upd = True  
        log_msg(logFile, f"tree_upd = {self.tree_upd}")
        try:
            log_msg(logFile, f"tree_upd = {self.tree_upd}")
            # Отримати шлях до елемента
            full_path = self.get_item_path(item)  
            value = item.text()

            # Оновлення self.xml_tree
            self.update_xml_tree(full_path, value)

            # Емітуємо сигнал dataChangedInTree для підключених компонентів
            # Передача змін у таблицю через сигнал dataChangedInTree
            log_msg(logFile, f"try: emit dataChangedInTree")
            self.dataChangedInTree.emit(full_path, value)
        finally:
            # Завершення синхронізації
            self.tree_upd = False
            log_msg(logFile, f"tree_upd = {self.tree_upd}")


    def update_xml_tree(self, full_path, value):
        """
        Оновлює self.xml_tree на основі full_path та value.
        """
        
        # приймає full_path та value як аргументи.
        # розбиває full_path на частини, щоб знайти відповідний елемент 
        # в self.xml_tree.
        # Він оновлює text знайденого елемента на value.
        # Додано обробку помилок, якщо елемент не знайдено.

        log_msg(logFile, f"full_path: {full_path}, value: {value}")
        if self.xml_tree is None:
            log_msg(logFile, "Error: self.xml_tree is None")
            return

        try:
            # Розділяємо шлях на частини
            path_parts = full_path.split("/")
            # Починаємо з кореневого елемента
            current_element = self.xml_tree.getroot()

            # Проходимо по частинах шляху, знаходячи відповідні елементи
            # Пропускаємо кореневий елемент
            for part in path_parts[1:]:  
                found = False
                for child in current_element:
                    if child.tag == part:
                        current_element = child
                        found = True
                        break
                if not found:
                    log_msg(logFile, f"Error: Element '{part}' not found in path '{full_path}'")
                    return

            # Оновлюємо значення елемента
            current_element.text = value
            log_msg(logFile, f"Element '{full_path}' updated with value '{value}'")
        except Exception as e:
            log_msg(logFile, f"Error updating XML tree: {e}")


    def get_key_item_path(self, item):
        """Отримує шлях до елемента в дереві"""
        log_msg(logFile)
        path = []
        while item:
            path.insert(0, item.text())
            item = item.parent()
        return "/".join(path)


    def editNode(self, item):
        """ Викликається, коли вузол дерева редагується.
        """
        log_msg(logFile)

        # Отримання повного шляху до елемента
        full_path = self.get_full_path(item)
        value = item.text()
        # Емітуємо сигнал із даними (шлях вузла та нове значення)
        self.dataChangedInTree.emit(full_path, value)
        return


    def load_allowed_dothers(self):  # after icon click

        """ 
            Завантаження списків дозволених дочірніх елементів

            Списки дозволених дочірніх елементів описуються в ini.
            Оскільки, не всім елементам дерева можна додавати дочірні.

        """
        log_msg(logFile, "")

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
                        # Перетворюємо кількість на число
                        limit = int(elements[i + 1])
                        self.allowed_dothers[path.strip()][element] = limit
                    except (IndexError, ValueError):
                        log_msg(
                            logFile, f"Помилка у секції [AllowedDothers] для шляху '{path.strip()}': {rules}")  # pylint: disable=line-too-long


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
                    #child_action.triggered.connect(self.create_add_child_callback(item, child_name))
                    connector.connect(child_action, "triggered", self.create_add_child_callback(item, child_name))
                    add_child_menu.addAction(child_action)

            if add_child_menu.actions():
                menu.addMenu(add_child_menu)

        # Відображення контекстного меню
        menu.exec_(self.viewport().mapToGlobal(position))

    def get_element_path(self, item):
        """ Побудова повного шляху до елемента дерева.

        """
        log_msg(logFile, f"{item.text()}")
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

        value = QStandardItem(xml_element.text.strip()
                              if xml_element.text else "")
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




    def expand_initial_elements(self):
        """ Розкриває задані елементи дерева після завантаження XML.

            Список елементів, які повинні бути розкриті після 
            завантаження elements_to_expand описується в ini.

        """
        
        # log_calls(logFile)

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
                # Беремо текст із колонки 0
                key = parent.child(item.row(), 0).text()
            else:
                # Якщо елемент кореневий
                key = self.model.item(item.row(), 0).text()
            path.insert(0, key)
            item = parent
        return "/".join(path)

    def set_column_width(self, column_index, width_percentage):

        # log_msg(logFile)
        total_width = self.viewport().width()
        column_width = int(total_width * width_percentage / 100)
        self.setColumnWidth(column_index, column_width)

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

    def tree_FileDate_update(self, path, value):
        """ Оновлює FileDate у дереві при зміні FileDate у таблиці
        """
        log_msg(logFile, f"{value}")
        index_FileDate = self.find_element_index(path)
        if not index_FileDate.isValid():
            log_msg(logFile, "Елемент FileDate не знайдено у дереві.")
            return
        item_FileDate = self.model.itemFromIndex(index_FileDate)
        item_FileDate.parent().child(item_FileDate.row(), 1).setText(value)

    def tree_FileGUID_update(self, path, value):
        """ Оновлює FileGUID у дереві при зміні FileGUID у таблиці
        """
        log_msg(logFile, f"{value}")
        index_FileGUID = self.find_element_index(path)
        if not index_FileGUID.isValid():
            log_msg(logFile, "Елемент FileGUID не знайдено у дереві.")
            return
        item_FileGUID = self.model.itemFromIndex(index_FileGUID)
        item_FileGUID.parent().child(item_FileGUID.row(), 1).setText(value)

    def tree_FormatVersion_update(self, path, value):
        """ Оновлює FormatVersion у дереві при зміні FormatVersion у таблиці
        """
        log_msg(logFile, f"{value}")
        index_FormatVersion = self.find_element_index(path)
        if not index_FormatVersion.isValid():
            log_msg(logFile, "Елемент FormatVersion не знайдено у дереві.")
            return
        item_FormatVersion = self.model.itemFromIndex(index_FormatVersion)
        item_FormatVersion.parent().child(item_FormatVersion.row(), 1).setText(value)

    def tree_ReceiverName_update(self, path, value):
        """ Оновлює ReceiverName у дереві при зміні ReceiverName у таблиці
        """
        log_msg(logFile, f"{value}")
        index_ReceiverName = self.find_element_index(path)
        if not index_ReceiverName.isValid():
            log_msg(logFile, "Елемент ReceiverName не знайдено у дереві.")
            return
        item_ReceiverName = self.model.itemFromIndex(index_ReceiverName)
        item_ReceiverName.parent().child(item_ReceiverName.row(), 1).setText(value)

    def tree_ReceiverIdentifier_update(self, path, value):
        """ Оновлює ReceiverIdentifier у дереві при зміні ReceiverIdentifier у таблиці
        """
        log_msg(logFile, f"{value}")
        index_ReceiverIdentifier = self.find_element_index(path)
        if not index_ReceiverIdentifier.isValid():
            log_msg(logFile, "Елемент ReceiverIdentifier не знайдено у дереві.")
            return
        item_ReceiverIdentifier = self.model.itemFromIndex(
            index_ReceiverIdentifier)
        item_ReceiverIdentifier.parent().child(
            item_ReceiverIdentifier.row(), 1).setText(value)

    def tree_Software_update(self, path, value):
        """ Оновлює Software у дереві при зміні Software у таблиці
        """
        log_msg(logFile, f"{value}")
        index_Software = self.find_element_index(path)
        if not index_Software.isValid():
            log_msg(logFile, "Елемент Software не знайдено у дереві.")
            return
        item_Software = self.model.itemFromIndex(index_Software)
        item_Software.parent().child(item_Software.row(), 1).setText(value)

    def tree_SoftwareVersion_update(self, path, value):
        """ Оновлює SoftwareVersion у дереві при зміні SoftwareVersion у таблиці
        """
        log_msg(logFile, f"{value}")
        index_SoftwareVersion = self.find_element_index(path)
        if not index_SoftwareVersion.isValid():
            log_msg(logFile, "Елемент SoftwareVersion не знайдено у дереві.")
            return
        item_SoftwareVersion = self.model.itemFromIndex(index_SoftwareVersion)
        item_SoftwareVersion.parent().child(item_SoftwareVersion.row(), 1).setText(value)

    def tree_CRS_update(self, full_path, value):
        """ Оновлює CRS у дереві при зміні CRS у таблиці
            Якщо value починається з починається SC63 то після "," -> {X,C,P,T}
        """
        log_msg(logFile, f"{value}")

        index_CRS = self.find_element_index(path=full_path, element_name=None)
        if not index_CRS.isValid():
            log_msg(logFile, "Елемент CoordinateSystem не знайдено у дереві.")
            return

        item_CRS = self.model.itemFromIndex(index_CRS)
        # ✔ 2025.01.30 10:32:42 CoordinateSystem
        log_msg(logFile, f"Знайдено вузол {item_CRS.text()}")
        # Треба знайти дочірній елемент CoordinateSystem
        # Якщо він не знайдений, то виходимо
        if item_CRS.rowCount() == 0:
            log_msg(logFile, f"Дочірній елемент CoordinateSystem не знайдено.")
            return
        log_msg(
            logFile, f"Елемент CoordinateSystem має {item_CRS.rowCount()} дочірніх елементів.")
        # Знаходимо дочірній елемент CoordinateSystem
        item_CRS_child = item_CRS.child(0)
        log_msg(logFile, f"Дочірній елемент {item_CRS_child.text()}")

        # Якщо стара CoordinateSystem SC63
        if item_CRS_child.text() == "SC63":

            # Якщо нова CoordinateSystem SC63
            if value.startswith("SC63,"):
                # то парсуємо новий район {X,C,P,T}
                sc63_region = value.split(",")[1].strip()
                log_msg(logFile, f"Новий SC63 район: {sc63_region}")
                # Знаходимо старий район - дочірній елемент SC63
                item_CRS_child_child = item_CRS_child.child(0)
                # Логуємо район
                log_msg(
                    logFile, f"Старий SC63 район {item_CRS_child_child.text()}")
                # Оновлюємо район
                item_CRS_child_child.setText(sc63_region)
                # Логуємо район
                log_msg(
                    logFile, f"Оновлений SC63 район {item_CRS_child_child.text()}")
            # Якщо нова CoordinateSystem Local
            elif value.startswith("Local"):
                # замінюємо SC63 на нову Local
                item_CRS_child.setText("Local")
                # знаходимо дочірній елемент Local
                item_CRS_child_child = item_CRS_child.child(0)
                # парсимо номер нової локальної CS, який знаходиться в дужках
                local_CS_number = value[value.find("(") + 1:value.find(")")]
                # Логуємо номер
                log_msg(
                    logFile, f"Новий номер локальної CS: {local_CS_number}")
                # Оновлюємо номер
                item_CRS_child_child.setText(local_CS_number)
            # Якщо нова CoordinateSystem інша
            else:
                # видаляємо старий район
                item_CRS_child.removeRows(0, item_CRS_child.rowCount())
                # замінюємо SC63 на нову
                item_CRS_child.setText(value)
        # Якщо стара CoordinateSystem Local
        elif item_CRS_child.text() == "Local":
            # Якщо нова CoordinateSystem SC63
            if value.startswith("SC63,"):
                # замінюємо Local на нову SC63
                item_CRS_child.setText("SC63")
                # знаходимо дочірній елемент SC63
                item_CRS_child_child = item_CRS_child.child(0)
                # парсимо номер нової SC63, який знаходиться після коми
                sc63_region = value.split(",")[1].strip()
                # Логуємо номер
                log_msg(logFile, f"Новий SC63 район: {sc63_region}")
                # Оновлюємо номер
                item_CRS_child_child.setText(sc63_region)
            # Якщо нова CoordinateSystem Local
            elif value.startswith("Local"):
                # парсимо номер нової локальної CS, який знаходиться в дужках
                local_CS_number = value[value.find("(") + 1:value.find(")")]
                # Логуємо номер
                log_msg(
                    logFile, f"Новий номер локальної CS: {local_CS_number}")
                # Оновлюємо номер
                item_CRS_child.child(0).setText(local_CS_number)
            # Якщо нова CoordinateSystem інша
            else:
                # видаляємо старий номер
                item_CRS_child.removeRows(0, item_CRS_child.rowCount())
                # замінюємо Local на нову
                item_CRS_child.setText(value)
        # Якщо стара CoordinateSystem інша (не SC63, не Local)
        else:
            # Якщо нова CoordinateSystem SC63
            if value.startswith("SC63,"):
                # знаходимо новий район
                sc63_region = value.split(",")[1].strip()
                # Замінюємо стару CoordinateSystem на SC63
                item_CRS_child.setText("SC63")
                # Додаємо новий район
                item_CRS_child.appendRow(
                    [QStandardItem(sc63_region), QStandardItem()])
            # Якщо нова CoordinateSystem Local
            elif value.startswith("Local"):
                # парсимо номер нової локальної CS, який знаходиться в дужках
                local_CS_number = value[value.find("(") + 1:value.find(")")]
                # Замінюємо стару CoordinateSystem на Local
                item_CRS_child.setText("Local")
                # Додаємо новий номер
                item_CRS_child.appendRow(
                    [QStandardItem(local_CS_number), QStandardItem()])
            # Якщо нова CoordinateSystem інша
            else:
                # Замінюємо стару CoordinateSystem на нову
                item_CRS_child.setText(value)
        # Логуємо результат
        log_msg(logFile, f"Оновлений CoordinateSystem: {value}")
        return

    def tree_HeightSystem_update(self, path, value):
        """ Оновлює HeightSystem у дереві при зміні HeightSystem у таблиці
        """
        log_msg(logFile, f"{value}")
        index_HeightSystem = self.find_element_index(path)
        if not index_HeightSystem.isValid():
            log_msg(logFile, "Елемент HeightSystem не знайдено у дереві.")
            return
        item_HeightSystem = self.model.itemFromIndex(index_HeightSystem)
        # знаходимо дочірній елемент HeightSystem
        item_HeightSystem_child = item_HeightSystem.child(0)
        # замінюємо його на новий
        item_HeightSystem_child.setText(value)

    def tree_MeasurementUnit_update(self, path, value):
        """ Оновлює MeasurementUnit у дереві при зміні MeasurementUnit у таблиці
        """
        log_msg(logFile, f"{value}")
        index_MeasurementUnit = self.find_element_index(path)
        if not index_MeasurementUnit.isValid():
            log_msg(logFile, "Елемент MeasurementUnit не знайдено у дереві.")
            return
        item_MeasurementUnit = self.model.itemFromIndex(index_MeasurementUnit)
        # знаходимо дочірній елемент MeasurementUnit
        item_MeasurementUnit_child = item_MeasurementUnit.child(0)
        # замінюємо його на новий
        item_MeasurementUnit_child.setText(value)

    def tree_CadastralZoneNumber_update(self, path, value):
        """ Оновлює CadastralZoneNumber у дереві при зміні CadastralZoneNumber у таблиці
        """
        log_msg(logFile, f"{value}")
        index_CadastralZoneNumber = self.find_element_index(path)
        if not index_CadastralZoneNumber.isValid():
            log_msg(logFile, "Елемент CadastralZoneNumber не знайдено у дереві.")
            return
        item_CadastralZoneNumber = self.model.itemFromIndex(
            index_CadastralZoneNumber)
        item_CadastralZoneNumber.parent().child(
            item_CadastralZoneNumber.row(), 1).setText(value)

    def tree_CadastralQuarterNumber_update(self, path, value):
        """ Оновлює CadastralQuarterNumber у дереві при зміні CadastralQuarterNumber у таблиці
        """
        log_msg(logFile, f"{value}")
        index_CadastralQuarterNumber = self.find_element_index(path)
        if not index_CadastralQuarterNumber.isValid():
            log_msg(logFile, "Елемент CadastralQuarterNumber не знайдено у дереві.")
            return
        item_CadastralQuarterNumber = self.model.itemFromIndex(
            index_CadastralQuarterNumber)
        item_CadastralQuarterNumber.parent().child(
            item_CadastralQuarterNumber.row(), 1).setText(value)

    def tree_ParcelID_update(self, path, value):
        """ Оновлює ParcelID у дереві при зміні ParcelID у таблиці
        """
        log_msg(logFile, f"{value}")
        index_ParcelID = self.find_element_index(path)
        if not index_ParcelID.isValid():
            log_msg(logFile, "Елемент ParcelID не знайдено у дереві.")
            return
        item_ParcelID = self.model.itemFromIndex(index_ParcelID)
        item_ParcelID.parent().child(item_ParcelID.row(), 1).setText(value)

    def tree_LocalAuthorityHead_update(self, path, value):
        """ Оновлює LocalAuthorityHead у дереві при зміні LocalAuthorityHead у таблиці
        """
        log_msg(logFile, f"{value}")
        index_LocalAuthorityHead = self.find_element_index(path)
        if not index_LocalAuthorityHead.isValid():
            log_msg(logFile, "Елемент LocalAuthorityHead не знайдено у дереві.")
            return
        # Парсимо value Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту.
        # У Ім'я та По батькові допускаються крапки, якщо є ініціали (наприклад, І.І.)
        # Якщо відсутній По батькові, то вказується тільки Прізвище та Ім'я
        # Прізвище, Ім'я та (за потреби) По батькові мають бути розділені пробілами
        # Прізвище, Ім'я та (за потреби) По батькові мають починатися з великої літери
        # Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту

        # Перевіряємо валідність значення
        if not self.validate_full_name(value):
            log_msg(logFile, f"Невірний формат значення '{value}'")
            return
        # Розділяємо значення на Прізвище, Ім'я та (за потреби) По батькові
        if len(value.split(" ")) == 2:
            surname, name = value.split(" ")
            MiddleName = ""
        else:
            surname, name, MiddleName = value.split(" ")
        # Логуємо знайдені значення
        log_msg(
            logFile, f"Прізвище: {surname}, Ім'я: {name}, По батькові: {MiddleName}")

        # Знаходимо елемент LocalAuthorityHead
        item_LocalAuthorityHead = self.model.itemFromIndex(
            index_LocalAuthorityHead)
        # Знаходимо дочірній елемент LocalAuthorityHead LastName
        item_LocalAuthorityHead_child_0 = item_LocalAuthorityHead.child(0)
        pathLastName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/LastName"
        # Знаходимо індекс елемента LastName
        index_LocalAuthorityHead_child_0 = self.find_element_index(
            pathLastName)
        # Змінюємо значення елемента у колонці 1
        item_LocalAuthorityHead_child_0.parent().child(item_LocalAuthorityHead_child_0.row(),
                                                       # ✔ 2025.01.30 15:11:08
                                                       1).setText(surname)
        # Знаходимо дочірній елемент LocalAuthorityHead FirstName
        item_LocalAuthorityHead_child_1 = item_LocalAuthorityHead.child(1)
        pathFirstName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/FirstName"
        # Знаходимо індекс елемента FirstName
        index_LocalAuthorityHead_child_1 = self.find_element_index(
            pathFirstName)
        # Змінюємо значення елемента у колонці 1
        item_LocalAuthorityHead_child_1.parent().child(
            item_LocalAuthorityHead_child_1.row(), 1).setText(name)
        # Якщо По батькові вказано
        # Знаходимо дочірній елемент LocalAuthorityHead MiddleName
        item_LocalAuthorityHead_child_2 = item_LocalAuthorityHead.child(2)
        pathMiddleName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/MiddleName"
        # Знаходимо індекс елемента MiddleName
        index_LocalAuthorityHead_child_2 = self.find_element_index(
            pathMiddleName)
        # Змінюємо значення елемента у колонці 1
        item_LocalAuthorityHead_child_2.parent().child(
            item_LocalAuthorityHead_child_2.row(), 1).setText(MiddleName)

    def tree_DKZRHead_update(self, path, value):
        """ Оновлює DKZRHead у дереві при зміні DKZRHead у таблиці
        """
        log_msg(logFile, f"{value}")
        index_DKZRHead = self.find_element_index(path)
        if not index_DKZRHead.isValid():
            log_msg(logFile, "Елемент DKZRHead не знайдено у дереві.")
            return
        # Парсимо value Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту.
        # У Ім'я та По батькові допускаються крапки, якщо є ініціали (наприклад, І.І.)
        # Якщо відсутній По батькові, то вказується тільки Прізвище та Ім'я
        # Прізвище, Ім'я та (за потреби) По батькові мають бути розділені пробілами
        # Прізвище, Ім'я та (за потреби) По батькові мають починатися з великої літери
        # Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту

        # Перевіряємо валідність значення
        if not self.validate_full_name(value):
            log_msg(logFile, f"Невірний формат значення '{value}'")
            return
        # Розділяємо значення на Прізвище, Ім'я та (за потреби) По батькові
        if len(value.split(" ")) == 2:
            surname, name = value.split(" ")
            MiddleName = ""
        else:
            surname, name, MiddleName = value.split(" ")
        # Логуємо знайдені значення
        log_msg(
            logFile, f"Прізвище: {surname}, Ім'я: {name}, По батькові: {MiddleName}")

        # Знаходимо елемент DKZRHead
        item_DKZRHead = self.model.itemFromIndex(index_DKZRHead)
        # Знаходимо дочірній елемент DKZRHead LastName
        item_DKZRHead_child_0 = item_DKZRHead.child(0)
        pathLastName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/LastName"
        # Знаходимо індекс елемента LastName
        index_DKZRHead_child_0 = self.find_element_index(pathLastName)
        # Змінюємо значення елемента у колонці 1
        item_DKZRHead_child_0.parent().child(item_DKZRHead_child_0.row(),
                                             # ✔ 2025.01.30 15:11:08
                                             1).setText(surname)
        # Знаходимо дочірній елемент DKZRHead FirstName
        item_DKZRHead_child_1 = item_DKZRHead.child(1)
        pathFirstName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/FirstName"
        # Знаходимо індекс елемента FirstName
        index_DKZRHead_child_1 = self.find_element_index(pathFirstName)
        # Змінюємо значення елемента у колонці 1
        item_DKZRHead_child_1.parent().child(item_DKZRHead_child_1.row(), 1).setText(name)
        # Якщо По батькові вказано
        # Знаходимо дочірній елемент DKZRHead MiddleName
        item_DKZRHead_child_2 = item_DKZRHead.child(2)
        pathMiddleName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/MiddleName"
        # Знаходимо індекс елемента MiddleName
        index_DKZRHead_child_2 = self.find_element_index(pathMiddleName)
        # Змінюємо значення елемента у колонці 1
        item_DKZRHead_child_2.parent().child(
            item_DKZRHead_child_2.row(), 1).setText(MiddleName)

    def extract_descriptions(self, element, full_path="", ns=None, is_root=False):
        """
        Рекурсивно витягує описи з XSD для елементів, включаючи вкладені структури.
        """
        name = element.get("name")
        ref = element.get("ref")

        if ref:
            # Якщо використовується ref, знайти елемент за ref
            ref_element = element.getroottree().xpath(
                f"//xsd:element[@name='{ref}']", namespaces=ns)  # pylint: disable=line-too-long
            if ref_element:
                self.extract_descriptions(
                    ref_element[0], full_path, ns, is_root=False)
            else:
                print(f"Reference '{ref}' not found in XSD.")
            return

        if name:
            # Формуємо повний шлях
            full_path = f"{full_path}/{name}".strip("/") if full_path else name

            # Витягуємо документацію
            documentation = element.xpath(
                './xsd:annotation/xsd:documentation', namespaces=ns)
            if documentation:
                self.xsd_descriptions[full_path] = documentation[0].text.strip(
                )

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
                ref_element = element.getroottree().xpath(
                    f"//xsd:complexType[@name='{ref_type}'] | //xsd:simpleType[@name='{ref_type}']", namespaces=ns)  # pylint: disable=line-too-long
                if ref_element:
                    print(
                        f"Processing type reference '{ref_type}' for element '{name}'")
                    for ref_child in ref_element[0].xpath('./xsd:sequence/xsd:element | ./xsd:choice/xsd:element | ./xsd:all/xsd:element', namespaces=ns):  # pylint: disable=line-too-long
                        self.extract_descriptions(ref_child, full_path, ns)

    def load_xsd_descriptions(self, path_to_xsd: str):
        """
        Парсує XSD-файл і витягує описи для елементів.
        Формує словник, де ключ — повний шлях до елемента, значення — опис.
        """
        # log_msg(logFile, )

        self.xsd_descriptions = {}
        try:
            # Парсинг XSD
            xsd_tree = etree.parse(
                path_to_xsd)  # pylint: disable=c-extension-no-member
            root = xsd_tree.getroot()
            # Простір імен для xsd
            ns = {'xsd': 'http://www.w3.org/2001/XMLSchema'}

            # Знаходимо кореневий елемент
            root_element = root.xpath(
                "//xsd:element[@name='UkrainianCadastralExchangeFile']", namespaces=ns)  # pylint: disable=line-too-long
            if root_element:
                self.extract_descriptions(
                    root_element[0], "", ns, is_root=True)
            else:
                log_msg(
                    logFile, "Кореневий елемент 'UkrainianCadastralExchangeFile' не знайдено.")  # pylint: disable=line-too-long
        except Exception as e:
            log_msg(
                logFile, f"Помилка при парсингу XSD: {e}")  # pylint: disable=broad-except

        # log_dict(logFile, self.xsd_descriptions, msg="xsd_descriptions")
        return self.xsd_descriptions

    def _add_element_to_tree(self, element, parent_item, full_path=""):
        """ Рекурсивно додає XML-елементи до моделі дерева, встановлюючи підказки.
        """
        name = etree.QName(element).localname
        # log_msg(logFile, f"name = {name}")
        # Оновлюємо повний шлях
        if full_path:
            full_path = f"{full_path}/{name}"
        else:
            full_path = name
        # Створюємо елементи для моделі
        name_item = QStandardItem(name)
        value_item = QStandardItem(
            element.text.strip() if element.text else "")

        name_item.setData(full_path, Qt.UserRole)
        value_item.setData(full_path, Qt.UserRole)

        self.tree_row += 1
        name_item.setData(self.tree_row, Qt.UserRole + 1)
        value_item.setData(self.tree_row, Qt.UserRole + 1)
        name_item.setData(0, Qt.UserRole + 2)
        value_item.setData(1, Qt.UserRole + 2)

        # Встановлюємо підказку, якщо опис доступний
        description = self.xsd_descriptions.get(full_path, "")
        if description:
            name_item.setToolTip(description)
            value_item.setToolTip(description)

        # Забороняємо редагування ключа (назви)
        name_item.setEditable(False)
        value_item.setEditable(False)

        # Додаємо елементи до дерева
        parent_item.appendRow([name_item, value_item])
        # Рекурсивно додаємо дочірні елементи
        for child in element:
            self._add_element_to_tree(child, name_item, full_path)

    def load_xml_to_tree_view(self, 
            xml_path: str = "",
            path_to_xsd: str = "",
            tree: etree._ElementTree = None):

        # Ця функція першопочатково створює електронне дерево xml
        # при відкритті xml файла
        """
        Loads an XML file into a tree view and validates it against an XSD schema.
        Args:
            xml_path (str): The file path to the XML file to be loaded.
            path_to_xsd (str): The file path to the XSD schema for validation.
        Raises:
            Exception: If there is an error loading or parsing the XML file.
        """

        # Ця функція викликає рекурсивну функцію _add_element_to_tree
        # log_calls(logFile, f"xml_path = {xml_path}\npath_to_xsd = {path_to_xsd}\ntree = {tree}")

        self.tree_row = 0

        try:
            self.xsd_descriptions = self.load_xsd_descriptions(path_to_xsd)

            if tree:
                self.xml_tree = tree
            else:
                self.xml_tree = etree.parse(xml_path)

            # Очищаємо існуючу модель дерева при повторному відкритті XML
            self.model.removeRows(0, self.model.rowCount())

            root = self.xml_tree.getroot()

            # саме тут відбувається заповнення моделі дерева вкладки "Структура"
            # даними з xml_tree
            self._add_element_to_tree(root, self.model.invisibleRootItem())

            # після заповнення моделі дерева потрібно розкрити елементи 
            # дерева, які призначені бути розкритими expand_initial_elements

        except Exception as e:
            log_msg(logFile, f"Помилка при завантаженні XML: {e}")


    def save_xml_tree(self, xml_tree, xml_path):
        """
        Saves an lxml ElementTree object to a file.

        Args:
            xml_tree (etree._ElementTree): The lxml ElementTree object to save.
            xml_path (str): The file path where the XML should be saved.
        Raises:
            TypeError: If xml_tree is not an etree._ElementTree object.
            Exception: If there is an error saving the XML file.
        """

        # Метод save_xml_tree класу CustomTreeView відповідає 
        # за збереження XML-дерева на диск.
        # Він приймає об'єкт etree._ElementTree (xml_tree) 
        # та шлях до файлу (xml_path).
        # Він правильно використовує xml_tree.write() для 
        # запису даних у файл.
        # Але цей метод викликається лише при явній дії 
        # користувача "Зберегти" або "Зберегти як".

        try:
            xml_tree.write(xml_path, encoding="utf-8", xml_declaration=True)
            print(f"XML file successfully saved to: {xml_path}")
        except OSError as e:
            raise Exception(f"Error saving XML file to {xml_path}: {e}") from e




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
                # Припустимо, імена у першій колонці
                item = self.model.item(row, 0)
                if item and item.text() == element_name:
                    return self.model.indexFromItem(item)

        return QModelIndex()
