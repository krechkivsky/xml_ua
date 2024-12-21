# -*- coding: utf-8 -*-
# from PyQt5.QtWidgets import QApplication, QMainWindow, QDockWidget, QWidget
# from PyQt5.QtWidgets import QVBoxLayout,QHBoxLayout, QMenuBar, QMenu, QAction
# from PyQt5.QtWidgets import QPushButton, QMessageBox, QToolButton, QStyle
# from PyQt5.QtWidgets import QTreeView, QFileDialog, QInputDialog, QLineEdit
# from PyQt5.QtWidgets import QTreeView

from qgis.PyQt.QtWidgets import QApplication, QMainWindow, QDockWidget, QWidget
from qgis.PyQt.QtWidgets import QVBoxLayout,QHBoxLayout, QMenuBar, QMenu, QAction
from qgis.PyQt.QtWidgets import QPushButton, QMessageBox, QToolButton, QStyle
from qgis.PyQt.QtWidgets import QTreeView, QFileDialog, QInputDialog, QLineEdit
from qgis.PyQt.QtWidgets import QTreeView



from lxml import etree
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtCore import QModelIndex, Qt, pyqtSignal
import os, sys, inspect

from . import common
from . import metadata
from .date_delegate import DateMaskDelegate
from .date_dialog import DateInputDialog


class CustomTreeView(QTreeView):
    """

        Хоча клас називається CustomTreeView і наслідується від QTreeView
        у ньому (тимчасово) додатково описується ще tableViewMetadata,
        всі (більшість?) фукнкції якого описані у модулі metadata.py
        
        Правильно було б:
        1. Переназвати клас у CustomWidgets (наслідувати його від  QTreeView
            і QTadleView одночасно і перенести сюди всі функції з metadata.py
            або
        2. Створити новий клас CustomTableView у модулі metadata.py і
            переназвати його у custom_table_view.py
    """
    
    dataChangedSignal = pyqtSignal(str, str)  
    # Signal to synchronize data changes


    def __init__(self, parent=None, table_view_metadata=None):
        # table_view_metadata - резервування пераметра для отримання з батьківського
        # класу лінку на таблицю з метаданими
        
        super().__init__(parent)

        common.log_msg(common.logFile, f"table_view_metadata = {table_view_metadata}")
        
        self.xmlTree = None
        self.tableViewMetadata = table_view_metadata
        # Збереження посилання на tableViewMetadata у елемент класу
        
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
        
        self.model.itemChanged.connect(self.on_item_changed)
        self.dataChangedSignal.connect(self.on_data_changed)  # Підключення сигналу до обробника


    def load_xml_to_tree_view(self, xml_path: str, xsd_path: str):
        '''
            Завантажує XML у вигляд дерева та заповнює tableViewMetadata 
            даними розділу ServiceInfo.
        '''
        
        common.log_msg(common.logFile)
        common.log_stack(common.logFile, msg="Заповнення дерева Структури")
        
        parts = xml_path.split("/")
        xml_fn = parts[-1]
        parts = xsd_path.split("/")
        xsd_fn = parts[-1]

        try:
            # Парсимо XSD та будуємо словник описів
            self.xsd_descriptions = self.load_xsd_descriptions(xsd_path)
            
            # Парсимо XML
            self.xmlTree = etree.parse(xml_path)

            # Валідація XML за допомогою XSD
            xsd_tree = etree.parse(xsd_path)
            xsd_schema = etree.XMLSchema(xsd_tree)
            
            # if not xsd_schema.validate(xmlTree):
                # common.log_msg(common.logFile, f"XML не відповідає XSD:\n{xsd_schema.error_log}")

            # Очищаємо існуючу модель дерева Структури
            self.model.removeRows(0, self.model.rowCount())

            # Заповнюємо дерево
            root = self.xmlTree.getroot()
            self._add_element_to_tree(root, self.model.invisibleRootItem())
            

        except Exception as e:
            # Обробка виключень (логування, повідомлення користувачу тощо)
            common.log_msg(common.logFile, f"Помилка при завантаженні XML: {e}")


    def load_xsd_descriptions(self, xsd_path: str):
        """
        Парсує XSD-файл і витягує описи для елементів.
        Повертає словник, що зіставляє назви елементів з їх описами.
        """
        common.log_msg(common.logFile)
        descriptions = {}
        try:
            xsd_tree = etree.parse(xsd_path)
            root = xsd_tree.getroot()
            ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}

            # Знаходимо всі елементи з документацією
            for elem in root.xpath('//xs:element', namespaces=ns):
                name = elem.get('name')
                # common.log_msg(common.logFile, f"name = {name}")
                # Знаходимо документацію всередині елемента
                documentation = elem.xpath('.//xs:annotation/xs:documentation', namespaces=ns)
                if documentation:
                    # common.log_msg(common.logFile, f"description = {documentation[0].text.strip()}")
                    descriptions[name] = documentation[0].text.strip()
        except Exception as e:
            # print(f"Помилка при парсингу XSD: {e}")
            common.log_msg(common.logFile, f"Помилка при парсингу XSD: {e}")
        return descriptions


    def _add_element_to_tree(self, element, parent_item):
        """
        Рекурсивно додає XML-елементи до моделі дерева.
        """
        # common.log_msg(common.logFile)
        # Отримуємо назву елемента без простору імен
        name = etree.QName(element).localname

        # Створюємо основний елемент
        name_item = QStandardItem(name)

        # Забороняємо редагування в першій колонці
        name_item.setEditable(False)

        # Встановлюємо значення (текст елемента)
        value = element.text.strip() if element.text else ""
        # common.log_msg(common.logFile, f"value =  {str(value)}")
        value_item = QStandardItem(value)

        # Встановлюємо підказку, якщо опис доступний
        description = self.xsd_descriptions.get(name, "")
        # common.log_msg(common.logFile, f"description =  {description}")
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
        common.log_msg(common.logFile)
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
        common.log_msg(common.logFile)
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
        common.log_msg(common.logFile)
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
        common.log_msg(common.logFile)
        if item.text().isdigit():
            QMessageBox.information(self, "Валідність", "Значення є валідним числом.")
        else:
            QMessageBox.warning(self, "Валідність", "Значення не є валідним числом!")


    def add_child_item(self):
        """
        Додає дочірній елемент до вибраного елемента.
        """
        common.log_msg(common.logFile)
        index = self.currentIndex()
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
        common.log_msg(common.logFile)
        index = self.currentIndex()
        # common.log_msg(common.logFile)
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        if item:
            parent = item.parent()
            if parent:
                parent.removeRow(item.row())
            else:
                self.model.removeRow(item.row())


    def on_item_changed(self, item):
        """
        Обробка зміни елемента в TreeView.
        Це також оновлює відповідне значення в таблиці.
        """
        common.log_msg(common.logFile)
        if item.column() == 1:  # Оновлюємо тільки значення
            # Отримує шлях до зміненого елемента в дереві через метод get_item_path
            path = self.get_item_path(item)
            value = item.text()

            common.log_msg(common.logFile, f"item path = {path}")
            common.log_msg(common.logFile, f"item value = {value}")

            # Емітує сигнал dataChangedSignal для синхронізації змін із таблицею
            self.dataChangedSignal.emit(path, value)


    def expand_initial_elements(self):
        """
            Розкриває лише задані елементи у CustomTreeView після завантаження XML.
        
            :param self: Віджет типу CustomTreeView.
            :param common.elements_to_expand: Список тегів елементів, які потрібно розкрити.
        """
        # common.log_msg(common.logFile)
    
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


    def get_item_path(self, item):
        """
        Отримує шлях до елемента в TreeView.
        """
        common.log_msg(common.logFile)
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
        common.log_msg(common.logFile)
        total_width = self.viewport().width()
        column_width = int(total_width * width_percentage / 100)
        self.setColumnWidth(column_index, column_width)


    def synchronize_metadata(self, table_view_metadata):
        """
        Синхронізує дані між treeViewXML і tableViewMetadata.
        """
        common.log_msg(common.logFile)
        metadata_model = table_view_metadata.model()
        if not metadata_model:
            common.log_msg(common.logFile, "Модель tableViewMetadata не встановлена.")
            return

        for row in range(metadata_model.rowCount()):
            key_item = metadata_model.item(row, 0)
            value_item = metadata_model.item(row, 1)

            if key_item and value_item:
                path = key_item.text()
                value = value_item.text()

                # Знаходимо елемент у TreeView і оновлюємо його значення
                index = self.find_element_index(path)
                if index.isValid():
                    tree_item = self.model().itemFromIndex(index)
                    if tree_item:
                        tree_item.setText(value)


    # def populate_tableview_metadata(self, xmlTree, table_view_metadata):
    def populate_tableview_metadata(self, xmlTree, table_view_metadata, metadata_tooltips):
        """
            Ця функція є методом класу CustomTreeView
            
            а мала б бути методом окремого класу CustomTableView 
            для таблиці метаданих
            
            Заповнює tableViewMetadata даними розділу ServiceInfo 
            та встановлює повний шлях у UserRole.
            Налаштовує ширину нульової колонки відповідно до вмісту.
            Вимикає редагування та вибір елементів таблиці.
        """
        common.log_msg(common.logFile)
        common.log_dict(common.logFile, metadata_tooltips, msg="metadata_tooltips")
        
        root_tag = "UkrainianCadastralExchangeFile"
        service_info_path = f"{root_tag}/AdditionalPart/ServiceInfo"
        service_info_element = xmlTree.find("./AdditionalPart/ServiceInfo")
    
        if service_info_element is None:
            common.log_msg(self.logFile, f"Розділ ServiceInfo не знайдено.")
            return
    
        metadata_model = QStandardItemModel()
        metadata_model.setHorizontalHeaderLabels(["Елемент", "Значення"])
        table_view_metadata.setModel(metadata_model)
        
        # Створення та встановлення делегата
        # delegate = DateDelegate(self.tableViewMetadata)
        delegate = DateMaskDelegate(self.tableViewMetadata)
        self.tableViewMetadata.setItemDelegateForColumn(1, delegate)  # Для стовпця 1





        tooltip_mapping = {}  # Новий словник для tooltips
        
        for child in service_info_element:
            if child.tag == "FileID":
                # Розбиваємо FileID на FileDate та FileGUID
                file_date = child.find("FileDate")
                file_guid = child.find("FileGUID")
    
                if file_date is not None:
                    full_path = f"{service_info_path}/FileID/FileDate"
                    ukr_description = self.get_tooltip_from_tree(full_path, "FileDate")
                    tooltip_mapping[ukr_description] = metadata_tooltips.get("FileDate", "")  # Додаємо tooltip
                    
                    key_item = QStandardItem(ukr_description)
                    value_item = QStandardItem(file_date.text.strip() if file_date.text else "")
                    key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
                    
                    # Вимикаємо редагування для елементів таблиці
                    key_item.setEditable(False)
                    value_item.setEditable(True)
                    
                    metadata_model.appendRow([key_item, value_item])
    
                if file_guid is not None:
                    full_path = f"{service_info_path}/FileID/FileGUID"
                    ukr_description = self.get_tooltip_from_tree(full_path, "FileGUID")
                    tooltip_mapping[ukr_description] = metadata_tooltips.get("FileGUID", "")  # Додаємо tooltip

                    key_item = QStandardItem(ukr_description)
                    value_item = QStandardItem(file_guid.text.strip() if file_guid.text else "")
                    key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
                    
                    # Вимикаємо редагування для елементів таблиці
                    key_item.setEditable(False)
                    value_item.setEditable(True)
                    
                    metadata_model.appendRow([key_item, value_item])
            else:
                full_path = f"{service_info_path}/{child.tag}"
                ukr_description = self.get_tooltip_from_tree(full_path, child.tag)
                tooltip_mapping[ukr_description] = metadata_tooltips.get(child.tag, "")  # Додаємо tooltip
                
                key_item = QStandardItem(ukr_description)
                value_item = QStandardItem(child.text.strip() if child.text else "")
                key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
                
                # Вимикаємо редагування для елементів таблиці
                key_item.setEditable(False)
                value_item.setEditable(True)
                
                metadata_model.appendRow([key_item, value_item])
    
        table_view_metadata.resizeColumnToContents(0)
    
        # Встановлюємо tooltips для таблиці, використовуючи новий словник
        metadata.set_tooltips_for_table(metadata_model, tooltip_mapping)
        
        metadata_model.itemChanged.connect(self.on_metadata_item_changed)



    # def populate_tableview_metadata(self, xml_tree, table_view_metadata, metadata_tooltips):
    # # def populate_tableview_metadata(self, xmlTree, table_view_metadata):
        # """
            # Заповнює tableViewMetadata даними розділу ServiceInfo та встановлює повний шлях у UserRole.
            # Налаштовує ширину нульової колонки відповідно до вмісту.
            # Створює словник для tooltips, де ключами є українські описи, а значеннями — текст підказки з INI.
            
            # викликається з load_data() при обробці події process_action_open():
            
            # Параметри:
                # self                - екземпляр CustomTreeView
                # xml_tree            - дерево
                # table_view_metadata - таблиця
                # metadata_tooltips   - словник підказок з ini файлу

        # """
        # # common.log_object_model(common.logFile, table_view_metadata)
    
        # common.log_msg(common.logFile, "")
        
        # root_tag = "UkrainianCadastralExchangeFile"
        # service_info_path = f"{root_tag}/AdditionalPart/ServiceInfo"
        # service_info_element = xml_tree.find("./AdditionalPart/ServiceInfo")
        
        # if service_info_element is None:
            # common.log_var(self.logFile, f"Розділ ServiceInfo в ini не знайдено.")
            # return
    
        # metadata_model = table_view_metadata.model()
        
        
        # tooltip_mapping = {}  # Новий словник для tooltips
    
        # for child in service_info_element:
            # if child.tag == "FileID":
                # # Розбиваємо FileID на FileDate та FileGUID
                # file_date = child.find("FileDate")
                # file_guid = child.find("FileGUID")
    
                # if file_date is not None:
                    # full_path = f"{service_info_path}/FileID/FileDate"
                    # ukr_description = self.get_tooltip_from_tree(full_path, "FileDate")
                    # tooltip_mapping[ukr_description] = metadata_tooltips.get("FileDate", "")  # Додаємо tooltip
                    
                    # key_item = QStandardItem(ukr_description)
                    # value_item = QStandardItem(file_date.text.strip() if file_date.text else "")
                    # key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
                    
                    # # Вимикаємо редагування для елементів таблиці
                    # key_item.setEditable(False)
                    # value_item.setEditable(True)
                    
                    # metadata_model.appendRow([key_item, value_item])
    
                # if file_guid is not None:
                    # full_path = f"{service_info_path}/FileID/FileGUID"
                    # ukr_description = self.get_tooltip_from_tree(full_path, "FileGUID")
                    # tooltip_mapping[ukr_description] = metadata_tooltips.get("FileGUID", "")  # Додаємо tooltip
                    
                    # key_item = QStandardItem(ukr_description)
                    # value_item = QStandardItem(file_guid.text.strip() if file_guid.text else "")
                    # key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
                    
                    # # Вимикаємо редагування для елементів таблиці
                    # key_item.setEditable(False)
                    # value_item.setEditable(True)
                    
                    # metadata_model.appendRow([key_item, value_item])
            # else:
                # full_path = f"{service_info_path}/{child.tag}"
                # ukr_description = self.get_tooltip_from_tree(full_path, child.tag)
                # tooltip_mapping[ukr_description] = metadata_tooltips.get(child.tag, "")  # Додаємо tooltip
                
                # key_item = QStandardItem(ukr_description)
                # value_item = QStandardItem(child.text.strip() if child.text else "")
                # key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
                
                # # Вимикаємо редагування для елементів таблиці
                # key_item.setEditable(False)
                # value_item.setEditable(True)
                
                # metadata_model.appendRow([key_item, value_item])
    
        # table_view_metadata.resizeColumnToContents(0)
    
        # # Встановлюємо tooltips для таблиці, використовуючи новий словник
        # set_tooltips_for_table(metadata_model, tooltip_mapping)
        # common.log_dict(common.logFile, self.tooltip_mapping, msg="tooltip_mapping")
    
        # metadata_model.itemChanged.connect(self.on_metadata_item_changed)



   
    def on_metadata_item_changed(self, item):
        """
        Обробка зміни елемента в tableViewMetadata.
        """
        common.log_msg(common.logFile)
        row = item.row()
        key_item = item.model().item(row, 0)
        value_item = item.model().item(row, 1)
    
        if not key_item or not value_item:
            common.log_msg(self.logFile, "Ключ або значення елемента таблиці відсутні.")
            return
    
        # Отримуємо шлях із UserRole
        path = key_item.data(Qt.UserRole)
        if not path:
            common.log_msg(self.logFile, "Шлях елемента таблиці дорівнює None.")
            return
    
        value = value_item.text()
    
        # Оновлюємо відповідний елемент у TreeView
        index = self.find_element_index(path)
        if index.isValid():
            tree_item = self.model.itemFromIndex(index)
            if tree_item:
                # Оновлюємо текст у колонці 1 (значення вузла)
                tree_item.parent().child(tree_item.row(), 1).setText(value)
                common.log_msg(common.logFile, f"Оновлено значення у дереві: {path} -> {value}")
        else:
            common.log_msg(common.logFile, f"Елемент не знайдено у дереві: {path}")


    def log_tree_structure(self):
        """
        Виводить усі шляхи у дереві для діагностики.
        """
        common.log_msg(common.logFile)
        def traverse_tree(item, path=""):
            path = f"{path}/{item.text()}" if path else item.text()
            common.log_msg(common.logFile, f"Tree path: {path}")
            for row in range(item.rowCount()):
                traverse_tree(item.child(row, 0), path)
    
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            traverse_tree(root.child(row, 0))


    def find_element_index(self, element_path):
        """
        Пошук елемента у моделі TreeView за повним шляхом.
        """
        common.log_msg(common.logFile)
        parts = element_path.split("/")
        parent_index = QModelIndex()
    
        for part in parts:
            found = False
            for row in range(self.model.rowCount(parent_index)):
                index = self.model.index(row, 0, parent_index)
                if index.data() == part:
                    parent_index = index
                    found = True
                    break
    
            if not found:
                return QModelIndex()
    
        return parent_index


    def get_tooltip_from_tree(self, full_path, default_name):
        """
        Отримує tooltip для елемента з дерева за його шляхом.
        Якщо tooltip не знайдено, повертає default_name.
        """
        common.log_msg(common.logFile)  
        tree_index = self.find_element_index(full_path)  # Пошук елемента за шляхом
        if tree_index.isValid():
            tree_item = self.model.itemFromIndex(tree_index)
            if tree_item:
                return tree_item.toolTip() or default_name  # Повертає tooltip або default_name
        return default_name


    def on_data_changed(self, path, value):
        """
        Оновлює відповідне значення в tableViewMetadata після зміни в дереві.
        """
        common.log_msg(common.logFile)
        metadata_model = self.tableViewMetadata.model()  # Отримуємо модель таблиці
        if metadata_model:
            # Шукаємо елемент у таблиці за шляхом
            for row in range(metadata_model.rowCount()):
                key_item = metadata_model.item(row, 0)
                if key_item and key_item.data(Qt.UserRole) == path:
                    value_item = metadata_model.item(row, 1)
                    if value_item:
                        value_item.setText(value)  # Оновлюємо значення в таблиці
                        break
