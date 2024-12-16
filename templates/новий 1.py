# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QApplication, QMainWindow, QDockWidget, QWidget, QVBoxLayout,QHBoxLayout, QMenuBar, QMenu, QAction, QPushButton, QMessageBox, QToolButton, QStyle,QTreeView, QFileDialog,QInputDialog,QLineEdit
from PyQt5.QtWidgets import QTreeView
from lxml import etree
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtCore import Qt
import os, sys, inspect, chardet

from . import common


class CustomTreeView(QTreeView):

    def __init__(self, parent=None):
        # logging(common.logFile, f"self: {str(self)}")
        super().__init__(parent)


        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Елемент", "Значення"])
        self.setModel(self.model)
        self.xsd_descriptions = {}

        # Налаштовуємо політику прокрутки
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Політика контекстного меню
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    # def get_element_full_path(self, element):
        # """Генерація повного шляху елемента."""
        # # logging(common.logFile)
        # path = []
        # while element is not None:
            # name = element.attrib.get("name", "NoName")
            # path.insert(0, name)
            # element = element.getparent()
        # return "/".join(path)

    def load_xml_to_tree_view(self, xml_path: str, xsd_path: str, table_view):
        '''
            Завантажує XML у вигляд дерева та заповнює tableViewMetadata 
            даними розділу ServiceInfo.
        '''

        logging(common.logFile, f"table_view: {table_view}")
        parts = xml_path.split("/")
        xml_fn = parts[-1]
        parts = xsd_path.split("/")
        xsd_fn = parts[-1]
        logging(common.logFile, f"{xml_fn}, {xsd_fn}")
        try:
            # Парсимо XSD та будуємо словник описів
            self.xsd_descriptions = self.load_xsd_descriptions(xsd_path)
            
            # Парсимо XML
            xml_tree = etree.parse(xml_path)

            # Валідація XML за допомогою XSD
            xsd_tree = etree.parse(xsd_path)
            xsd_schema = etree.XMLSchema(xsd_tree)
            
            # if not xsd_schema.validate(xml_tree):
                # logging(common.logFile, f"XML не відповідає XSD:\n{xsd_schema.error_log}")

            # Очищаємо існуючу модель
            self.model.removeRows(0, self.model.rowCount())

            # Заповнюємо дерево
            root = xml_tree.getroot()

            self._add_element_to_tree(root, self.model.invisibleRootItem())
            
            self.populate_tableview_metadata(xml_tree, table_view)

        except Exception as e:
            # Обробка виключень (логування, повідомлення користувачу тощо)
            logging(common.logFile, f"Помилка при завантаженні XML: {e}")
        
    
        # # Отримання метаданих
        # metadata = self.get_metadata_values(xml_tree)
    
        # # Оновлення моделі QTableView (припустимо, що у вас є змінна self.tableViewMetadata)
        # # table_view.model().clear()
        # for key, value in metadata.items():
            # item_name = QStandardItem(key)
            # item_value = QStandardItem(value)
            # self.table_view.model().appendRow([item_name, item_value])
            # logging(common.logFile, f"item_name: {item_name} item_value: {item_value}")


    def load_xsd_descriptions(self, xsd_path: str):
        """
        Парсує XSD-файл і витягує описи для елементів.
        Повертає словник, що зіставляє назви елементів з їх описами.
        """
        # logging(common.logFile, f"xsd_path = {xsd_path}")
        descriptions = {}
        try:
            xsd_tree = etree.parse(xsd_path)
            root = xsd_tree.getroot()
            ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}

            # Знаходимо всі елементи з документацією
            for elem in root.xpath('//xs:element', namespaces=ns):
                name = elem.get('name')
                # logging(common.logFile, f"name = {name}")
                # Знаходимо документацію всередині елемента
                documentation = elem.xpath('.//xs:annotation/xs:documentation', namespaces=ns)
                if documentation:
                    # logging(common.logFile, f"description = {documentation[0].text.strip()}")
                    descriptions[name] = documentation[0].text.strip()
        except Exception as e:
            # print(f"Помилка при парсингу XSD: {e}")
            logging(common.logFile, f"Помилка при парсингу XSD: {e}")
        return descriptions

    def _add_element_to_tree(self, element, parent_item):
        """
        Рекурсивно додає XML-елементи до моделі дерева.
        """
        # Отримуємо назву елемента без простору імен
        name = etree.QName(element).localname

        # Створюємо основний елемент
        name_item = QStandardItem(name)

        # Встановлюємо значення (текст елемента)
        value = element.text.strip() if element.text else ""
        # logging(common.logFile, f"value =  {str(value)}")
        value_item = QStandardItem(value)

        # Встановлюємо підказку, якщо опис доступний
        description = self.xsd_descriptions.get(name, "")
        # logging(common.logFile, f"description =  {description}")
        if description:
            name_item.setToolTip(description)
            value_item.setToolTip(description)

        # Додаємо рядок до батьківського елемента
        parent_item.appendRow([name_item, value_item])

        # Рекурсивно додаємо дочірні елементи
        for child in element:
            self._add_element_to_tree(child, name_item)

    def create_tree_item(self, xml_element, parent_path):
        """Рекурсивне створення дерева."""
        # logging(common.logFile)
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

    def show_context_menu(self, position):
        """Показує контекстне меню для елемента."""
        logging(common.logFile)
        index = self.indexAt(position)
        if not index.isValid():
            return

        item = self.model.itemFromIndex(index)
        column = index.column()

        menu = QMenu(self)

        if column == 1:  # Колонка значень
            change_value_action = menu.addAction("Змінити значення")
            change_value_action.triggered.connect(lambda: self.change_value())

            validate_action = menu.addAction("Перевірити валідність")
            validate_action.triggered.connect(lambda: self.validate_value(item))

        elif column == 0:  # Колонка назв
            # add_child_action = menu.addAction("Додати дочірній елемент")
            # add_child_action.triggered.connect(lambda: self.add_child_item())
            pass

        delete_action = menu.addAction("Видалити елемент")
        # delete_action.triggered.connect(lambda: self.delete_item(item))
        delete_action.triggered.connect(lambda: self.delete_item())

        menu.exec_(self.viewport().mapToGlobal(position))

    def change_value(self):
        """
        Змінює значення вибраного елемента.
        """
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
        """Перевіряє валідність значення."""
        logging(common.logFile)
        if item.text().isdigit():
            QMessageBox.information(self, "Валідність", "Значення є валідним числом.")
        else:
            QMessageBox.warning(self, "Валідність", "Значення не є валідним числом!")

    def add_child_item(self):
        """
        Додає дочірній елемент до вибраного елемента.
        """
        index = self.currentIndex()
        logging(common.logFile)
        if not index.isValid():
            return
        parent_item = self.model.itemFromIndex(index)
        if parent_item:
            child_name = "Новий елемент"
            child_item = QStandardItem(child_name)
            child_item.setToolTip("Опис нового елемента")  # Український опис
            parent_item.appendRow([child_item, QStandardItem("")])

    def delete_item(self):
        """
        Видаляє вибраний елемент.
        """
        index = self.currentIndex()
        # logging(common.logFile)
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        if item:
            parent = item.parent()
            if parent:
                parent.removeRow(item.row())
            else:
                self.model.removeRow(item.row())

    def expand_initial_elements(self):
        """
        Розкриває лише задані елементи у CustomTreeView після завантаження XML.
    
        :param self: Віджет типу CustomTreeView.
        :param common.elements_to_expand: Список тегів елементів, які потрібно розкрити.
        """
        # logging(common.logFile)
    
        # Отримання моделі дерева
        model = self.model
        if model is None:
            return
    
        def expand_recursively(index):
            """
            Рекурсивно розкриває вузли дерева, якщо їхній тег у списку common.elements_to_expand.
    
            :param index: Індекс поточного елемента в моделі.
            """
            item = model.itemFromIndex(index)
            if item is None:
                return
    
            # Перевірка, чи потрібно розкрити елемент
            if item.text() in common.elements_to_expand:
                self.expand(index)
    
            # Обхід дочірніх елементів
            for row in range(item.rowCount()):
                child_index = model.index(row, 0, index)
                expand_recursively(child_index)
    
        # Початковий вузол
        root_index = model.index(0, 0)
        expand_recursively(root_index)

    def set_column_width(self, column_index, width_percentage):
        """
        Встановлює ширину колонки у відсотках від ширини CustomTreeView.
    
        :param self: Віджет типу CustomTreeView.
        :param column_index: Індекс колонки для зміни ширини.
        :param width_percentage: Ширина колонки у відсотках від загальної ширини TreeView (0-100).
        """
        # logging(common.logFile, f"self: {str(self)}")
        total_width = self.viewport().width()
        column_width = int(total_width * width_percentage / 100)
        self.setColumnWidth(column_index, column_width)

    def populate_tableview_metadata(self, xml_tree, table_view_metadata):
        """
        Заповнює tableViewMetadata даними розділу ServiceInfo.
        """
        service_info_path = "./AdditionalPart/ServiceInfo"
        service_info_element = xml_tree.find(service_info_path)

        if service_info_element is None:
            logging(common.logFile, f"Розділ ServiceInfo не знайдено за шляхом {service_info_path}.")
            return

        metadata_model = QStandardItemModel()
        metadata_model.setHorizontalHeaderLabels(["Key", "Value"])
        table_view_metadata.setModel(metadata_model)

        for child in service_info_element:
            key_item = QStandardItem(child.tag)
            value_item = QStandardItem(child.text.strip() if child.text else "")
            metadata_model.appendRow([key_item, value_item])






def caller():
    return inspect.stack()[2].function

def logging(logFile, msg=""):
    logFile.write(f"<.{os.path.basename(__file__)}:{sys._getframe().f_back.f_lineno}> {caller()}(): {msg}\n")
    logFile.flush()

def log_dict(logFile, dict, name: str = ""):
    msg = f"<.{os.path.basename(__file__)}:{sys._getframe().f_back.f_lineno}> {caller()}(): {name}"
    for key, value in dict.items():
        msg += '\n\t' + f"{key}: {value}"
    logFile.write(f"{msg}\n")
    logFile.flush()

def log_list(list, name: str = ""):
    msg = f"<.{os.path.basename(__file__)}:{sys._getframe().f_back.f_lineno}> {caller()}(): {name}:"
    for item in list:
        msg += '\n\t' + f"{item}"
    logFile.write(f"{msg}\n")
    logFile.flush()

# def log_xml(logFile, element, filter_tag, level=0):
    # logFile.write("\n")
    # indent = '  ' * level
    # logFile.write(f"{indent} {element.tag}")
    # for attribute in element.attrib:
        # if filter_tag != '' and element.tag == filter_tag: logFile.write(f"{indent}  {attribute}={element.attrib[attribute]}" + "\n")
    # for child in element:
        # log_xml(logFile, child, filter_tag, level+1)


def log_xml(logFile, element, filter_tag, level=0):
    # Перевіряємо, чи потрібно обробляти цей вузол
    if filter_tag and element.tag != filter_tag:
        logFile.write("\n")
        return

    # Друк тегу
    logFile.write("\n")
    indent = '  ' * level
    logFile.write(f"{indent}{element.tag}")

    # Друк атрибутів
    for attribute, value in element.attrib.items():
        logFile.write(f" {attribute}->{value}")

    # Обробка дочірніх елементів
    for child in element:
        log_xml(logFile, child, filter_tag, level + 1)