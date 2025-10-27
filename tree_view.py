# -*- coding: utf-8 -*-
# tree_view.py
"""Обробка XML дерева"""

import configparser
import re

import csv
import copy
import os
import uuid
from lxml import etree

from qgis.PyQt.QtWidgets import QMenu
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QStyle
from qgis.PyQt.QtWidgets import QTreeView
from qgis.PyQt.QtWidgets import QAbstractItemView
from qgis.PyQt.QtWidgets import QStyledItemDelegate
from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QIcon, QBrush, QColor
from qgis.PyQt.QtGui import QStandardItemModel
from qgis.PyQt.QtCore import QDate, QModelIndex
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import pyqtSignal

from .common import logFile
from .common import log_msg
from .common import config
from .common import connector
from .date_dialog import DateInputDialog
from .validators import validate_element
from .delegates import StateActTypeDelegate, CategoryDelegate, PurposeDelegate, OwnershipCodeDelegate, DocumentCodeDelegate, DispatcherDelegate, DocumentationTypeDelegate, LandCodeDelegate, ClosedDelegate


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

        self.parent = parent
        self.tree_upd = False   # Флаг для запобігання циклічним змінам
        self.xml_tree = None
        self.xsd_appinfo = {}
        self.xsd_descriptions = {}
        self.xsd_schema = {}
        self.restrictions_data = {}
        self.validation_errors = {} # Словник для зберігання помилок валідації

        self.tree_row = 0

        self.model = QStandardItemModel()
        self.setModel(self.model)

        self.model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        #self.model.itemChanged.connect(self.on_tree_model_data_changed)
        connector.connect(self.model, "itemChanged", self.on_tree_model_data_changed)
        self.group_name = ""

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        # Підключаємо контекстне меню
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_tree_view_context_menu)

        # Підключаємо обробник подвійного кліку
        self.doubleClicked.connect(self.on_double_click)

        self.allowed_dothers = {}
        self.load_allowed_dothers()
        self.elements_to_expand = config.get(
            "ElementsToExpand", "expanded").split(", ")

        # Встановлюємо кастомний делегат для колонки "Значення"
        self.state_act_delegate = StateActTypeDelegate(self)
        self.category_delegate = CategoryDelegate(self)
        self.purpose_delegate = PurposeDelegate(self)
        self.ownership_delegate = OwnershipCodeDelegate(self)
        self.doc_code_delegate = DocumentCodeDelegate(self)
        self.doc_type_delegate = DocumentationTypeDelegate(self)
        self.land_code_delegate = LandCodeDelegate(self)
        self.closed_delegate = ClosedDelegate(self)
        # Створюємо "диспетчер" делегатів і передаємо йому інші делегати
        self.dispatcher_delegate = DispatcherDelegate(
            parent=self,
            state_act_delegate=self.state_act_delegate,
            category_delegate=self.category_delegate,
            purpose_delegate=self.purpose_delegate,
            ownership_delegate=self.ownership_delegate,
            doc_code_delegate=self.doc_code_delegate,
            doc_type_delegate=self.doc_type_delegate,
            land_code_delegate=self.land_code_delegate,
            closed_delegate=self.closed_delegate
        )
        # Підключаємо сигнал від делегата до слота в CustomTreeView
        self.doc_type_delegate.documentationTypeChanged.connect(self.on_documentation_type_changed)

        self.setItemDelegateForColumn(1, self.dispatcher_delegate)

        # Завантажуємо дані про обмеження
        self.load_restrictions_data()


    def on_tree_model_data_changed(self, item):
        """
        Обробляє зміни даних у моделі дерева (QStandardItemModel).

        Цей метод є слотом, який автоматично викликається сигналом `itemChanged`
        від моделі дерева щоразу, коли користувач або програма змінює дані
        в будь-якому елементі (наприклад, через редагування значення у другій колонці).

        Основні дії:
        1. Встановлює флаг `self.tree_upd` для запобігання рекурсивним викликам.
        2. Визначає шлях та нове значення зміненого елемента.
        3. Викликає `update_xml_tree()` для синхронізації змін з внутрішнім XML-деревом (lxml).
        4. Викликає `mark_as_changed()` у батьківського док-віджета, щоб позначити файл як змінений.
        5. Випромінює сигнал `dataChangedInTree`, щоб інші компоненти (наприклад, таблиці) могли оновити свої дані.

        Викликається:
        - Автоматично сигналом `self.model.itemChanged` при будь-якій зміні даних в моделі.
        """
        # #log_msg(logFile, f"{item.text()}")
        # Якщо вже йде оновлення, нічого не робимо
        # if self.tree_upd:  
        #     #log_msg(logFile, "пропускаємо оновлення дерева")
        #     return

        # Початок синхронізації
        self.tree_upd = True  
        try:
            #log_msg(logFile, f"on_tree_model_data_changed: tree_upd = {self.tree_upd}")
            # Отримати шлях до елемента
            full_path = self.get_item_path(item)  
            value = item.text()

            # Оновлення self.xml_tree
            self.update_xml_tree(full_path, value)

            # Позначаємо файл як змінений у батьківському віджеті
            self.mark_as_changed() # Це оновить заголовок вкладки

            # Емітуємо сигнал dataChangedInTree для підключених компонентів
            # Передача змін у таблицю через сигнал dataChangedInTree
            # #log_msg(logFile, f"emit dataChangedInTree for path: {full_path}. Автоматична валідація вимкнена.")
            # Автоматична перевірка та підсвічування після зміни вимкнена за запитом користувача.
            # Валідація тепер викликається вручну через кнопку "Перевірити".
            self.dataChangedInTree.emit(full_path, value)
        finally:
            # Завершення синхронізації
            # Встановлюємо флаг у False після завершення всіх операцій
            self.tree_upd = False

    def update_xml_tree(self, full_path, value):
        """
        Оновлює self.xml_tree на основі full_path та value.
        """
        
        # приймає full_path та value як аргументи.
        # розбиває full_path на частини, щоб знайти відповідний елемент 
        # в self.xml_tree.
        # Він оновлює text знайденого елемента на value.
        # Додано обробку помилок, якщо елемент не знайдено.

        #log_msg(logFile, f"full_path: {full_path}, value: {value}")
        if self.xml_tree is None:
            #log_msg(logFile, "Error: self.xml_tree is None")
            return

        try:
            # Використовуємо XPath для пошуку елемента.
            # Шлях має бути відносним до кореня, тому починаємо з /
            xpath_expression = f"/{full_path}"
            elements = self.xml_tree.getroot().xpath(xpath_expression) # lxml вимагає xpath на кореневому вузлі дерева
            if elements:
                elements[0].text = value
                # #log_msg(logFile, f"Елемент '{full_path}' оновлено значенням '{value}'")
            else:
                log_msg(logFile, f"Помилка: Елемент за шляхом '{xpath_expression}' не знайдено в XML.")
        except Exception as e:
            log_msg(logFile, f"Error updating XML tree: {e}")

    def load_restrictions_data(self):
        """Завантажує та структурує дані з restrictions.csv."""
        # Змінено на .ini
        restrictions_path = os.path.join(os.path.dirname(__file__), 'templates', 'restriction.ini')
        if not os.path.exists(restrictions_path):
            log_msg(logFile, f"Файл з обмеженнями не знайдено: {restrictions_path}")
            return

        try:
            config = configparser.ConfigParser()
            # with open(restrictions_path, 'r', encoding='utf-8') as f:
            #     config.read_file(f)
            config.read(restrictions_path, encoding='utf-8')


            if 'RestrictionCode' in config:
                all_codes = dict(config['RestrictionCode'])
                for code, name in all_codes.items():
                    # Визначаємо код розділу (перші два символи)
                    section_code = code.split('.')[0]
                    if len(section_code) > 2: # для кодів типу '01', '02'
                        section_code = section_code[:2]

                    if section_code not in self.restrictions_data:
                        self.restrictions_data[section_code] = {}
                    self.restrictions_data[section_code][code] = name
        except Exception as e:
            log_msg(logFile, f"Помилка при читанні restriction.ini: {e}")

    def handle_restriction_code_menu(self, point, item):
        """Обробляє контекстне меню для вибору коду обмеження."""
        menu = QMenu()
        select_code_action = QAction("Вибрати код обмеження...", self)
        select_code_action.triggered.connect(lambda: self.select_restriction_code(item))
        menu.addAction(select_code_action)
        menu.exec_(self.viewport().mapToGlobal(point))

    def get_key_item_path(self, item):
        """Отримує шлях до елемента в дереві"""
        #log_msg(logFile)
        path = []
        while item:
            path.insert(0, item.text())
            item = item.parent()
        return "/".join(path)

    def get_key_item_path(self, item):
        """Отримує шлях до елемента в дереві"""
        #log_msg(logFile)
        path = []
        while item:
            path.insert(0, item.text())
            item = item.parent()
        return "/".join(path)


    def editNode(self, item):
        """ Викликається, коли вузол дерева редагується.
        """
        #log_msg(logFile)

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
        # #log_msg(logFile, "")

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

    def show_tree_view_context_menu(self, point):
        """
        Створює та показує контекстне меню для кореневого елемента у treeViewXML.
        """
        index = self.indexAt(point)
        if not index.isValid():
            return

        # Перевіряємо, чи клік був на кореневому елементі (у якого немає батька)
        if not index.parent().isValid():
            # Перевіряємо, чи є активний XML-файл
            if not self.parent.current_xml:
                return

            menu = QMenu()

            # Створюємо дії
            save_action = QAction(self.parent.plugin.action_save_tool.icon(), "Зберегти", self)
            save_as_template_action = QAction(self.parent.plugin.action_save_as_template_tool.icon(), "Зберегти як шаблон...", self)

            # Додаємо дії до меню
            menu.addAction(save_action)
            menu.addAction(save_as_template_action)

            close_action = QAction(self.style().standardIcon(QStyle.SP_DialogCloseButton), "Закрити", self)
            close_action.triggered.connect(lambda: self.parent.process_action_close_xml(self.parent.current_xml))
            menu.addAction(close_action)

            menu.addSeparator()

            # Показуємо меню у позиції курсора
            menu.exec_(self.viewport().mapToGlobal(point))
            return

        # Перевіряємо, чи клік був на елементі "Власники"
        item = self.model.itemFromIndex(index)
        item_path = item.data(Qt.UserRole)
        
        menu = QMenu()
        has_actions = False

        # Спеціальна логіка для CoordinateSystem
        coordinate_system_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/CoordinateSystem"
        if item_path == coordinate_system_path:
            menu = QMenu()
            has_actions = False

            # Перевіряємо, чи є що видаляти (тобто чи є дочірній елемент)
            if item.hasChildren():
                # Отримуємо перший дочірній елемент (напр., SC63, Local)
                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(f"Видалити систему координат '{child_item.text()}'", self)
                    # Використовуємо lambda, щоб передати правильний item для видалення
                    delete_action.triggered.connect(lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions and menu.exec_(self.viewport().mapToGlobal(point)):
                menu.exec_(self.viewport().mapToGlobal(point))
            # Не робимо return, щоб дозволити також спрацювати меню "Додати"

        # Спеціальна логіка для HeightSystem
        height_system_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/HeightSystem"
        if item_path == height_system_path:
            menu = QMenu()
            has_actions = False

            # Перевіряємо, чи є що видаляти (тобто чи є дочірній елемент)
            if item.hasChildren():
                # Отримуємо перший дочірній елемент (напр., Baltic)
                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(f"Видалити систему висот '{child_item.text()}'", self)
                    # Використовуємо lambda, щоб передати правильний item для видалення
                    delete_action.triggered.connect(lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions and menu.exec_(self.viewport().mapToGlobal(point)):
                menu.exec_(self.viewport().mapToGlobal(point))

        # Спеціальна логіка для MeasurementUnit
        measurement_unit_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/MeasurementUnit"
        if item_path == measurement_unit_path:
            menu = QMenu()
            has_actions = False

            # Перевіряємо, чи є що видаляти (тобто чи є дочірній елемент)
            if item.hasChildren():
                # Отримуємо перший дочірній елемент (напр., Meters)
                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(f"Видалити одиницю виміру '{child_item.text()}'", self)
                    # Використовуємо lambda, щоб передати правильний item для видалення
                    delete_action.triggered.connect(lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions:
                menu.exec_(self.viewport().mapToGlobal(point))
            # Не робимо return, щоб дозволити також спрацювати меню "Додати"

        # Спеціальна логіка для ParcelLocation
        parcel_location_path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/ParcelLocation"
        if item_path == parcel_location_path:
            menu = QMenu()
            has_actions = False

            # Перевіряємо, чи є що видаляти (тобто чи є дочірній елемент)
            if item.hasChildren():
                # Отримуємо перший дочірній елемент (напр., City)
                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(f"Видалити місцезнаходження '{child_item.text()}'", self)
                    # Використовуємо lambda, щоб передати правильний item для видалення
                    delete_action.triggered.connect(lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions and menu.exec_(self.viewport().mapToGlobal(point)):
                menu.exec_(self.viewport().mapToGlobal(point))
            # Не робимо return, щоб дозволити також спрацювати меню "Додати"

        # --- Логіка для додавання дочірніх елементів ---
        if item_path in self.xsd_schema:
            element_schema = self.xsd_schema[item_path]
            xml_element = self._find_xml_element_by_path(item_path)

            if xml_element is not None and 'children' in element_schema:
                add_menu = QMenu("Додати", self)
                added_to_add_menu = False
                for child_info in element_schema['children']:
                    child_tag = child_info['name']
                    max_occurs = child_info.get('maxOccurs', 1)
                    
                    # Рахуємо існуючі дочірні елементи
                    current_count = len(xml_element.findall(child_tag))

                    if max_occurs == 'unbounded' or current_count < int(max_occurs):
                        child_ukr_name = self.xsd_appinfo.get(f"{item_path}/{child_tag}", child_tag)
                        add_action = QAction(f"{child_ukr_name}", self)
                        add_action.triggered.connect(
                            lambda _, p_item=item, c_tag=child_tag: self.add_child_element(p_item, c_tag)
                        )
                        add_menu.addAction(add_action)
                        added_to_add_menu = True

                if added_to_add_menu:
                    if has_actions:
                        menu.addSeparator()
                    menu.addMenu(add_menu)
                    has_actions = True

        # --- Логіка для видалення елемента ---
        parent_item = item.parent()
        if parent_item:
            parent_path = parent_item.data(Qt.UserRole)
            if parent_path in self.xsd_schema:
                parent_schema = self.xsd_schema[parent_path]
                parent_xml_element = self._find_xml_element_by_path(parent_path)
                
                if parent_xml_element is not None and 'children' in parent_schema:
                    item_tag = item_path.split('/')[-1]
                    for child_info in parent_schema['children']:
                        if child_info['name'] == item_tag:
                            min_occurs = child_info.get('minOccurs', 1)
                            current_count = len(parent_xml_element.findall(item_tag))

                            if current_count > int(min_occurs):
                                if has_actions and not menu.actions()[-1].isSeparator(): menu.addSeparator()
                                delete_action = QAction(f"Видалити '{item.text()}'", self)
                                delete_action.triggered.connect(lambda _, it=item: self.delete_element(it))
                                menu.addAction(delete_action)
                                has_actions = True
                            break

        if has_actions:
            menu.exec_(self.viewport().mapToGlobal(point))

    def show_item_error_dialog(self, item_path):
        """Показує діалогове вікно з помилками для конкретного елемента."""
        if item_path in self.validation_errors:
            errors = self.validation_errors[item_path]
            error_text = "\n- ".join(errors)
            
            # Отримуємо українську назву для шляху
            ukr_path = self._generate_ukr_path(item_path)

            QMessageBox.warning(self, 
                                f"Помилки в елементі",
                                f"Для елемента:\n<b>{ukr_path}</b>\n\nЗнайдено наступні помилки:\n- {error_text}")

    def mark_as_changed(self):
        """Позначає поточний XML-файл як змінений."""
        # self.parent - це екземпляр dockwidget, переданий при ініціалізації
        if self.parent and hasattr(self.parent, 'mark_as_changed'):
            self.parent.mark_as_changed()

    def get_expanded_indexes(self, index, expanded_list):
        """
        Рекурсивно збирає шляхи розкритих елементів.
        """
        if self.isExpanded(index):
            item = self.model.itemFromIndex(index)
            if item:
                # Зберігаємо шлях до елемента як ідентифікатор
                path = item.data(Qt.UserRole)
                if path:
                    expanded_list.append(path)

        for row in range(self.model.rowCount(index)):
            child_index = self.model.index(row, 0, index)
            self.get_expanded_indexes(child_index, expanded_list)

    def restore_expanded_indexes(self, expanded_list):
        """
        Відновлює розкриті елементи за їхніми шляхами.
        """
        if not expanded_list:
            return

        def find_and_expand(parent_index):
            """Рекурсивний пошук та розкриття елементів."""
            for row in range(self.model.rowCount(parent_index)):
                index = self.model.index(row, 0, parent_index)
                item = self.model.itemFromIndex(index)
                if item:
                    path = item.data(Qt.UserRole)
                    if path in expanded_list:
                        self.expand(index)

                    if self.model.hasChildren(index):
                        find_and_expand(index)

        find_and_expand(self.model.invisibleRootItem().index())

    def update_view_from_tree(self):
        """
        Примусово оновлює відображення дерева на основі поточного стану self.xml_tree.
        """
        #log_msg(logFile, "Оновлення значень у дереві GUI.")
        if self.xml_tree is None:
            return

        # Рекурсивна функція для оновлення значень
        def update_items(parent_item):
            for row in range(parent_item.rowCount()):
                name_item = parent_item.child(row, 0)
                value_item = parent_item.child(row, 1)
                if name_item and value_item:
                    full_path = name_item.data(Qt.UserRole)
                    if full_path:
                        # Знаходимо відповідний елемент в оновленому XML-дереві
                        xml_element = self._find_xml_element_by_path(full_path)
                        if xml_element is not None:
                            new_value = xml_element.text.strip() if xml_element.text else ""
                            if value_item.text() != new_value:
                                value_item.setText(new_value)
                    # Рекурсивно оновлюємо дочірні елементи
                    if name_item.hasChildren():
                        update_items(name_item)

        update_items(self.model.invisibleRootItem())

    def on_documentation_type_changed(self, doc_type_code, index):
        """Слот, який реагує на зміну типу документації та оновлює список документів."""
        self.doc_type_delegate.update_document_list(doc_type_code, index)

    def rebuild_tree_view(self):
        """
        Повністю перебудовує дерево, зберігаючи розкриті вузли.
        Використовується, коли структура XML значно змінюється.
        """
        if self.xml_tree is None:
            return

        # 1. Зберігаємо список розкритих вузлів
        expanded_list = []
        self.get_expanded_indexes(self.rootIndex(), expanded_list)

        # 2. Перезавантажуємо дерево з поточного стану self.xml_tree
        self.load_xml_to_tree_view(tree=self.xml_tree)

        # 3. Відновлюємо розкриті вузли
        self.restore_expanded_indexes(expanded_list)

    def select_restriction_code(self, item):
        """Запускає двокроковий діалог вибору коду обмеження."""
        if not self.restrictions_data:
            QMessageBox.warning(self, "Помилка", "Дані про обмеження не завантажено.")
            return

        # Етап 1: Вибір основного коду (2-значного)
        main_codes = {code: name for section in self.restrictions_data.values() for code, name in section.items() if len(code) == 2}
        main_code_display_names = sorted([f"{code} - {name}" for code, name in main_codes.items()])

        dialog1 = QInputDialog(self)
        dialog1.setFixedWidth(800)
        dialog1.setLabelText("Виберіть розділ:")
        dialog1.setComboBoxItems(main_code_display_names)
        dialog1.setWindowTitle("Вибір розділу обмеження")
        ok = dialog1.exec_()
        main_code_selection = dialog1.textValue()

        if not ok or not main_code_selection:
            return

        selected_main_code = main_code_selection.split(' - ')[0]
        selected_code = selected_main_code

        # Перевірка, чи потрібен другий етап
        sub_codes_exist = any(code.startswith(selected_main_code + '.') for section in self.restrictions_data.values() for code in section)

        # Коди, для яких не потрібен другий крок, навіть якщо є підкоди
        single_step_codes = {'10', '11', '12', '13', '14'}

        if sub_codes_exist and selected_main_code not in single_step_codes:
            # Етап 2: Вибір уточненого коду
            sub_codes = {}
            if selected_main_code in self.restrictions_data:
                sub_codes = {code: name for code, name in self.restrictions_data[selected_main_code].items() if code.startswith(selected_main_code + '.')}

            if sub_codes:
                # Додаємо також і основний код до списку вибору
                sub_codes[selected_main_code] = main_codes[selected_main_code]
                
                sub_code_display_names = sorted([f"{code} - {name}" for code, name in sub_codes.items()])

                dialog2 = QInputDialog(self)
                dialog2.setFixedWidth(800)
                dialog2.setLabelText("Виберіть код:")
                dialog2.setComboBoxItems(sub_code_display_names)
                dialog2.setWindowTitle("Уточнення коду обмеження")
                ok = dialog2.exec_()
                sub_code_selection = dialog2.textValue()

                if ok and sub_code_selection:
                    selected_code = sub_code_selection.split(' - ')[0]
                elif not ok: # Якщо користувач натиснув "Скасувати" на другому етапі
                    return
                # Якщо користувач нічого не вибрав, але натиснув "ОК", використовуємо основний код

        # Отримуємо назву для вибраного коду
        selected_name = ""
        for section in self.restrictions_data.values():
            if selected_code in section:
                selected_name = section[selected_code]
                break

        # Оновлюємо значення в моделі
        item.setText(selected_code)

        # Тепер оновлюємо RestrictionName
        # `item` - це value_item для RestrictionCode. Його "брат" - name_item. Їхній батько - name_item для RestrictionInfo.
        if item.parent():
            # Батьківський елемент для пари (name, value) - це name_item для RestrictionInfo
            restriction_info_item = item.parent()
            if restriction_info_item:
                # Шукаємо дочірній елемент RestrictionName
                for row in range(restriction_info_item.rowCount()):
                    child_name_item = restriction_info_item.child(row, 0)
                    if child_name_item and child_name_item.text() == self.xsd_appinfo.get(f"{restriction_info_item.data(Qt.UserRole)}/RestrictionName", "RestrictionName"):
                        # Знайшли RestrictionName, оновлюємо його значення
                        restriction_name_value_item = restriction_info_item.child(row, 1)
                        if restriction_name_value_item:
                            restriction_name_value_item.setText(selected_name)
                        break

    def on_double_click(self, index):
        """Обробляє подвійний клік на елементі дерева."""
        if not index.isValid() or index.column() != 1:
            return

        item = self.model.itemFromIndex(index)
        if not item:
            return

        item_path = item.data(Qt.UserRole)
        if item_path and item_path.endswith("Date"):
            self.handle_date_edit(item)
        elif item_path and item_path.endswith("/FileID/FileGUID"):
            # Обробка подвійного кліку на GUID
            # Генеруємо новий GUID
            new_guid = str(uuid.uuid4()).upper()
            
            # Запитуємо підтвердження
            reply = QMessageBox.question(self, 'Перегенерація GUID',
                                         f"Згенерувати новий унікальний ідентифікатор файлу?\n\nНовий GUID: {new_guid}",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                # Оновлюємо значення в дереві. Сигнал itemChanged автоматично оновить XML.
                item.setText(new_guid)
        elif item_path and item_path.endswith("/ParcelLocationInfo/Region"):
            # Обробка подвійного кліку на Регіон
            self.handle_region_edit(item)

    def on_documentation_type_changed(self, doc_type_code, index):
        """Слот, який реагує на зміну типу документації та оновлює список документів."""
        self.doc_type_delegate.update_document_list(doc_type_code, index)

    def handle_date_edit(self, item):
        """Відкриває діалог редагування дати та оновлює значення."""
        current_value = item.text()
        default_date = QDate.fromString(current_value, "yyyy-MM-dd")
        if not default_date.isValid():
            default_date = QDate.currentDate()

        dialog = DateInputDialog(default_date=default_date, parent=self)

        if dialog.exec_() == QDialog.Accepted:
            new_date_str = dialog.get_date()
            # Перевіряємо, чи значення дійсно змінилося, щоб уникнути зайвих оновлень
            if new_date_str != current_value:
                item.setText(new_date_str)
                # Сигнал itemChanged буде викликаний автоматично,
                # що призведе до оновлення XML через on_tree_model_data_changed

    def handle_region_edit(self, item):
        """Відкриває діалог вибору регіону та оновлює значення."""
        if 'Region' not in config:
            QMessageBox.warning(self, "Помилка", "Секція [Region] не знайдена у файлі конфігурації.")
            return

        region_dict = dict(config['Region'])
        # Сортуємо за назвою регіону
        sorted_regions = sorted(region_dict.values())
        
        current_text = item.text()
        
        current_index = -1
        if current_text in sorted_regions:
            current_index = sorted_regions.index(current_text)

        selected_region, ok = QInputDialog.getItem(self, "Вибір регіону",
                                                     "Виберіть регіон:", sorted_regions,
                                                     current_index, False)

        if ok and selected_region:
            # Отримуємо повну назву регіону
            new_name = selected_region
            if new_name != current_text:
                # Оновлюємо значення в дереві. Сигнал itemChanged автоматично оновить XML.
                item.setText(new_name)

    def rebuild_tree_view(self):
        """
        Повністю перебудовує дерево, зберігаючи розкриті вузли.
        Використовується, коли структура XML значно змінюється.
        """
        if self.xml_tree is None:
            return

        # 1. Зберігаємо список розкритих вузлів
        expanded_list = []
        self.get_expanded_indexes(self.rootIndex(), expanded_list)

        # 2. Перезавантажуємо дерево з поточного стану self.xml_tree
        self.load_xml_to_tree_view(tree=self.xml_tree)

        # 3. Відновлюємо розкриті вузли
        self.restore_expanded_indexes(expanded_list)


    def add_child_element(self, parent_item, child_tag):
        """Додає дочірній елемент в XML та в дерево GUI."""
        parent_path = parent_item.data(Qt.UserRole)
        parent_xml_element = self._find_xml_element_by_path(parent_path)
        if parent_xml_element is None:
            #log_msg(logFile, f"Не вдалося знайти батьківський XML елемент для {parent_path}")
            return

        # Створюємо новий XML елемент
        new_xml_element = etree.Element(child_tag)
        new_xml_element.text = " " # Додаємо пробіл, щоб тег не був самозакриваючим
        parent_xml_element.append(new_xml_element)

        # Додаємо елемент в GUI
        child_path = f"{parent_path}/{child_tag}"
        name_item, value_item = self._create_qt_items_for_element(new_xml_element, child_path)
        parent_item.appendRow([name_item, value_item])

        # Робимо значення нового елемента доступним для редагування
        value_item.setEditable(True)

        # Позначаємо файл як змінений
        self.parent.mark_as_changed()
        self.expand(parent_item.index())

    def delete_element(self, item):
        """Видаляє елемент з XML та з дерева GUI."""
        LAYER_TO_XML_PATH = {
            "Суміжники": ".//AdjacentUnits",
            "Обмеження": ".//Restrictions",
            "Суборенда": ".//Subleases",
            "Оренда": ".//Leases",
            "Угіддя": ".//LandsParcel"
        }
        # Створюємо зворотний словник для пошуку назви шару за шляхом XML
        XML_PATH_TO_LAYER = {v: k for k, v in LAYER_TO_XML_PATH.items()}
        PROTECTED_PATHS = [
            ".//ParcelMetricInfo", # Ділянка
            ".//CadastralQuarterInfo", # Квартал
            ".//CadastralZoneInfo", # Зона
            ".//Polyline", # Полілінії
            ".//PointInfo" # Вузли
        ]

        item_path = item.data(Qt.UserRole)
        # Перевіряємо, чи шлях не є захищеним
        if any(item_path.endswith(p.split('/')[-1]) for p in PROTECTED_PATHS):
            QMessageBox.warning(self, "Видалення заборонено", f"Видалення елемента '{item.text()}' та відповідного йому шару заборонено.")
            #log_msg(logFile, f"Спроба видалення захищеного елемента '{item_path}' заблокована.")
            return

        xml_element_to_delete = self._find_xml_element_by_path(item_path)

        if xml_element_to_delete is None:
            log_msg(logFile, f"Не вдалося знайти XML елемент для видалення: {item_path}")
            return

        parent_xml_element = xml_element_to_delete.getparent()
        if parent_xml_element is None:
            log_msg(logFile, f"Не вдалося видалити елемент без батька: {item_path}")
            return

        # --- Початок змін: Виправлення порядку видалення та очищення ---
        is_adjacent_unit = False
        if xml_element_to_delete.tag == 'AdjacentUnitInfo':
            is_adjacent_unit = True
            # 1. Видаляємо відповідний об'єкт з карти
            self.parent.delete_adjacent_from_map(xml_element_to_delete)

        # 2. Видаляємо елемент з XML-дерева
        try:
            parent_xml_element.remove(xml_element_to_delete)
        except ValueError as e:
            # Перехоплюємо помилку, яка може виникнути, якщо елемент вже було видалено
            # внаслідок іншої операції (напр. cleanup_geometry).
            log_msg(logFile, f"Перехоплено очікувану помилку при видаленні вузла: {e}")

        # 3. Якщо це був суміжник, запускаємо безпечне очищення геометрії
        if is_adjacent_unit:
            from .topology import GeometryProcessor
            processor = GeometryProcessor(self.parent.current_xml.tree)
            # Передаємо список з одним видаленим елементом
            processor.cleanup_geometry([xml_element_to_delete])

        # --- Кінець змін ---

        # 4. Видаляємо з моделі GUI
        # 5. Видаляємо відповідний шар з карти, якщо це був останній елемент
        layer_name_to_remove = XML_PATH_TO_LAYER.get(f".//{item_path.split('/')[-1]}")
        if layer_name_to_remove and self.parent.layers_obj:
            self.parent.layers_obj.removeLayer(layer_name_to_remove, self.parent.current_xml.group_name)
            #log_msg(logFile, f"Шар '{layer_name_to_remove}' видалено з карти.")

        # 6. Позначаємо файл як змінений
        self.parent.mark_as_changed()

    def _find_xml_element_by_path(self, path):
        """Знаходить елемент в self.xml_tree за XPath."""
        if self.xml_tree is None:
            return None
        if not path:
            return None

        root = self.xml_tree.getroot()
        
        # Перевірка, чи підтримує об'єкт метод xpath (тобто чи це lxml)
        if hasattr(root, 'xpath'):
            elements = root.xpath(f"/{path}") # noqa
            return elements[0] if elements else None
        else: # Fallback для стандартного xml.etree
            return root.find(path)
        
    def get_element_path(self, item):
        """ Побудова повного шляху до елемента дерева.

        """
        #log_msg(logFile, f"{item.text()}")
        path = []
        while item:
            path.insert(0, item.text())
            item = item.parent()

        return "/" + "/".join(path)

    def get_current_child_count(self, parent_item, child_name):
        """
        Підраховує кількість дочірніх елементів із зазначеним іменем.
        """
        #log_msg(logFile)
        count = 0
        for i in range(parent_item.rowCount()):
            if parent_item.child(i).text() == child_name:
                count += 1
        return count

    def create_add_child_callback(self, parent_item, child_name):
        """
        Створює замикання для додавання дочірнього елемента.
        """
        #log_msg(logFile)
        return lambda: self.add_child(parent_item, child_name)

    def add_child(self, item, child_name):
        """
        Додає дочірній елемент до вказаного елемента дерева.
        """
        #log_msg(logFile)
        child_item = QStandardItem(child_name)
        child_item.setEditable(False)  # Забороняємо редагування назви елемента
        item.appendRow([child_item, QStandardItem("")])

    def change_value(self):
        """
        Змінює значення вибраного елемента.
        """
        #log_msg(logFile)
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
        #log_msg(logFile)
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
        #log_msg(logFile)
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

            # Отримуємо повний шлях елемента, який зберігається в Qt.UserRole
            item_full_path = item.data(Qt.UserRole)
            if item_full_path:
                # Витягуємо технічну назву тега з повного шляху
                item_tag_name = item_full_path.split('/')[-1]
                # Перевіряємо, чи потрібно розкрити елемент за його технічною назвою
                if item_tag_name in self.elements_to_expand:
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
        if not item:
            return ""
        # Шлях зберігається в першій колонці (name_item)
        if item.column() == 0: # Якщо зміна на name_item (хоча вони read-only)
            name_item = item
        else: # Якщо зміна на value_item (колонка 1)
            name_item = item.parent().child(item.row(), 0) if item.parent() else self.model.item(item.row(), 0)
        
        path = name_item.data(Qt.UserRole) if name_item else ""
        # #log_msg(logFile, f"get_item_path for '{item.text()}' -> '{path}'")
        return path

    def validate_full_name(self, full_name):
        """
        Перевіряє ПІБ на відповідність формату:
        - Прізвище, Ім'я та (за потреби) По батькові
            мають містити тільки літери українського алфавіту.
        - У Ім'я та По батькові допускаються крапки.
        """
        #log_msg(logFile)
        pattern = r"^[А-ЯІЇЄҐ][а-яіїєґ']+ [А-ЯІЇЄҐ][а-яіїєґ'\.]+(?: [А-ЯІЇЄҐ][а-яіїєґ'\.]+)?$"
        return bool(re.match(pattern, full_name))

    def tree_FileDate_update(self, path, value):
        """ Оновлює FileDate у дереві при зміні FileDate у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_FileDate = self.find_element_index(path)
        if not index_FileDate.isValid():
            #log_msg(logFile, "Елемент FileDate не знайдено у дереві.")
            return
        item_FileDate = self.model.itemFromIndex(index_FileDate)
        item_FileDate.parent().child(item_FileDate.row(), 1).setText(value)

    def tree_FileGUID_update(self, path, value):
        """ Оновлює FileGUID у дереві при зміні FileGUID у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_FileGUID = self.find_element_index(path)
        if not index_FileGUID.isValid():
            #log_msg(logFile, "Елемент FileGUID не знайдено у дереві.")
            return
        item_FileGUID = self.model.itemFromIndex(index_FileGUID)
        item_FileGUID.parent().child(item_FileGUID.row(), 1).setText(value)

    def tree_FormatVersion_update(self, path, value):
        """ Оновлює FormatVersion у дереві при зміні FormatVersion у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_FormatVersion = self.find_element_index(path)
        if not index_FormatVersion.isValid():
            #log_msg(logFile, "Елемент FormatVersion не знайдено у дереві.")
            return
        item_FormatVersion = self.model.itemFromIndex(index_FormatVersion)
        item_FormatVersion.parent().child(item_FormatVersion.row(), 1).setText(value)

    def tree_ReceiverName_update(self, path, value):
        """ Оновлює ReceiverName у дереві при зміні ReceiverName у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_ReceiverName = self.find_element_index(path)
        if not index_ReceiverName.isValid():
            #log_msg(logFile, "Елемент ReceiverName не знайдено у дереві.")
            return
        item_ReceiverName = self.model.itemFromIndex(index_ReceiverName)
        item_ReceiverName.parent().child(item_ReceiverName.row(), 1).setText(value)

    def tree_ReceiverIdentifier_update(self, path, value):
        """ Оновлює ReceiverIdentifier у дереві при зміні ReceiverIdentifier у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_ReceiverIdentifier = self.find_element_index(path)
        if not index_ReceiverIdentifier.isValid():
            #log_msg(logFile, "Елемент ReceiverIdentifier не знайдено у дереві.")
            return
        item_ReceiverIdentifier = self.model.itemFromIndex(
            index_ReceiverIdentifier)
        item_ReceiverIdentifier.parent().child(
            item_ReceiverIdentifier.row(), 1).setText(value)

    def tree_Software_update(self, path, value):
        """ Оновлює Software у дереві при зміні Software у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_Software = self.find_element_index(path)
        if not index_Software.isValid():
            #log_msg(logFile, "Елемент Software не знайдено у дереві.")
            return
        item_Software = self.model.itemFromIndex(index_Software)
        item_Software.parent().child(item_Software.row(), 1).setText(value)

    def tree_SoftwareVersion_update(self, path, value):
        """ Оновлює SoftwareVersion у дереві при зміні SoftwareVersion у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_SoftwareVersion = self.find_element_index(path)
        if not index_SoftwareVersion.isValid():
            #log_msg(logFile, "Елемент SoftwareVersion не знайдено у дереві.")
            return
        item_SoftwareVersion = self.model.itemFromIndex(index_SoftwareVersion)
        item_SoftwareVersion.parent().child(item_SoftwareVersion.row(), 1).setText(value)

    def tree_CRS_update(self, full_path, value):
        """ Оновлює CRS у дереві при зміні CRS у таблиці
            Якщо value починається з починається SC63 то після "," -> {X,C,P,T}
        """
        #log_msg(logFile, f"{value}")

        index_CRS = self.find_element_index(path=full_path, element_name=None)
        if not index_CRS.isValid():
            #log_msg(logFile, "Елемент CoordinateSystem не знайдено у дереві.")
            return

        item_CRS = self.model.itemFromIndex(index_CRS)
        # ✔ 2025.01.30 10:32:42 CoordinateSystem
        #log_msg(logFile, f"Знайдено вузол {item_CRS.text()}")
        # Треба знайти дочірній елемент CoordinateSystem
        # Якщо він не знайдений, то виходимо
        if item_CRS.rowCount() == 0:
            #log_msg(logFile, f"Дочірній елемент CoordinateSystem не знайдено.")
            return
        log_msg(
            logFile, f"Елемент CoordinateSystem має {item_CRS.rowCount()} дочірніх елементів.")
        # Знаходимо дочірній елемент CoordinateSystem
        item_CRS_child = item_CRS.child(0)
        #log_msg(logFile, f"Дочірній елемент {item_CRS_child.text()}")

        # Якщо стара CoordinateSystem SC63
        if item_CRS_child.text() == "SC63":

            # Якщо нова CoordinateSystem SC63
            if value.startswith("SC63,"):
                # то парсуємо новий район {X,C,P,T}
                sc63_region = value.split(",")[1].strip()
                #log_msg(logFile, f"Новий SC63 район: {sc63_region}")
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
                #log_msg(logFile, f"Новий SC63 район: {sc63_region}")
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
        #log_msg(logFile, f"Оновлений CoordinateSystem: {value}")
        return

    def tree_HeightSystem_update(self, path, value):
        """ Оновлює HeightSystem у дереві при зміні HeightSystem у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_HeightSystem = self.find_element_index(path)
        if not index_HeightSystem.isValid():
            #log_msg(logFile, "Елемент HeightSystem не знайдено у дереві.")
            return
        item_HeightSystem = self.model.itemFromIndex(index_HeightSystem)
        # знаходимо дочірній елемент HeightSystem
        item_HeightSystem_child = item_HeightSystem.child(0)
        # замінюємо його на новий
        item_HeightSystem_child.setText(value)

    def tree_MeasurementUnit_update(self, path, value):
        """ Оновлює MeasurementUnit у дереві при зміні MeasurementUnit у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_MeasurementUnit = self.find_element_index(path)
        if not index_MeasurementUnit.isValid():
            #log_msg(logFile, "Елемент MeasurementUnit не знайдено у дереві.")
            return
        item_MeasurementUnit = self.model.itemFromIndex(index_MeasurementUnit)
        # знаходимо дочірній елемент MeasurementUnit
        item_MeasurementUnit_child = item_MeasurementUnit.child(0)
        # замінюємо його на новий
        item_MeasurementUnit_child.setText(value)

    def tree_CadastralZoneNumber_update(self, path, value):
        """ Оновлює CadastralZoneNumber у дереві при зміні CadastralZoneNumber у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_CadastralZoneNumber = self.find_element_index(path)
        if not index_CadastralZoneNumber.isValid():
            #log_msg(logFile, "Елемент CadastralZoneNumber не знайдено у дереві.")
            return
        item_CadastralZoneNumber = self.model.itemFromIndex(
            index_CadastralZoneNumber)
        item_CadastralZoneNumber.parent().child(
            item_CadastralZoneNumber.row(), 1).setText(value)

    def tree_CadastralQuarterNumber_update(self, path, value):
        """ Оновлює CadastralQuarterNumber у дереві при зміні CadastralQuarterNumber у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_CadastralQuarterNumber = self.find_element_index(path)
        if not index_CadastralQuarterNumber.isValid():
            #log_msg(logFile, "Елемент CadastralQuarterNumber не знайдено у дереві.")
            return
        item_CadastralQuarterNumber = self.model.itemFromIndex(
            index_CadastralQuarterNumber)
        item_CadastralQuarterNumber.parent().child(
            item_CadastralQuarterNumber.row(), 1).setText(value)

    def tree_ParcelID_update(self, path, value):
        """ Оновлює ParcelID у дереві при зміні ParcelID у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_ParcelID = self.find_element_index(path)
        if not index_ParcelID.isValid():
            #log_msg(logFile, "Елемент ParcelID не знайдено у дереві.")
            return
        item_ParcelID = self.model.itemFromIndex(index_ParcelID)
        item_ParcelID.parent().child(item_ParcelID.row(), 1).setText(value)

    def tree_LocalAuthorityHead_update(self, path, value):
        """ Оновлює LocalAuthorityHead у дереві при зміні LocalAuthorityHead у таблиці
        """
        #log_msg(logFile, f"{value}")
        index_LocalAuthorityHead = self.find_element_index(path)
        if not index_LocalAuthorityHead.isValid():
            #log_msg(logFile, "Елемент LocalAuthorityHead не знайдено у дереві.")
            return
        # Парсимо value Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту.
        # У Ім'я та По батькові допускаються крапки, якщо є ініціали (наприклад, І.І.)
        # Якщо відсутній По батькові, то вказується тільки Прізвище та Ім'я
        # Прізвище, Ім'я та (за потреби) По батькові мають бути розділені пробілами
        # Прізвище, Ім'я та (за потреби) По батькові мають починатися з великої літери
        # Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту

        # Перевіряємо валідність значення
        if not self.validate_full_name(value):
            #log_msg(logFile, f"Невірний формат значення '{value}'")
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
        #log_msg(logFile, f"{value}")
        index_DKZRHead = self.find_element_index(path)
        if not index_DKZRHead.isValid():
            #log_msg(logFile, "Елемент DKZRHead не знайдено у дереві.")
            return
        # Парсимо value Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту.
        # У Ім'я та По батькові допускаються крапки, якщо є ініціали (наприклад, І.І.)
        # Якщо відсутній По батькові, то вказується тільки Прізвище та Ім'я
        # Прізвище, Ім'я та (за потреби) По батькові мають бути розділені пробілами
        # Прізвище, Ім'я та (за потреби) По батькові мають починатися з великої літери
        # Прізвище, Ім'я та (за потреби) По батькові мають містити тільки літери українського алфавіту

        # Перевіряємо валідність значення
        if not self.validate_full_name(value):
            #log_msg(logFile, f"Невірний формат значення '{value}'")
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
            
            # Витягуємо коротку назву
            appinfo = element.xpath(
                './xsd:annotation/xsd:appinfo', namespaces=ns)
            if appinfo:
                self.xsd_appinfo[full_path] = appinfo[0].text.strip()

            # Логування для перевірки
            # #log_msg(logFile, f"Extracted: {full_path} -> {self.xsd_appinfo.get(full_path, '')}")

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
        # #log_msg(logFile, )

        self.xsd_appinfo = {}
        self.xsd_descriptions = {}
        self.xsd_schema = {}
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
                self._parse_xsd_element(root_element[0], "", ns)
            else:
                log_msg(
                    logFile, "Кореневий елемент 'UkrainianCadastralExchangeFile' не знайдено.")  # pylint: disable=line-too-long
        except Exception as e:
            log_msg(
                logFile, f"Помилка при парсингу XSD: {e}")  # pylint: disable=broad-except

        # Логування перших 10 значень для контролю
        # #log_msg(logFile, "Перші 10 значень словника українських назв:")
        # count = 0
        # for path, name in self.xsd_appinfo.items():
        #     if count >= 10:
        #         break
        #     #log_msg(logFile, f"{path}: {name}")
        #     count += 1


        # log_dict(logFile, self.xsd_descriptions, msg="xsd_descriptions")
        return self.xsd_descriptions

    def _parse_xsd_element(self, element, parent_path, ns):
        """Рекурсивно парсить XSD, збираючи структуру, типи та обмеження."""
        tag_name = element.get('name')
        if not tag_name:
            ref = element.get('ref')
            if ref:
                # Знаходимо елемент за посиланням і продовжуємо парсинг
                ref_element = element.getroottree().xpath(f"//xsd:element[@name='{ref}']", namespaces=ns)
                if ref_element:
                    # Передаємо min/maxOccurs з посилання
                    ref_element[0].set('minOccurs', element.get('minOccurs', '1'))
                    ref_element[0].set('maxOccurs', element.get('maxOccurs', '1'))
                    return self._parse_xsd_element(ref_element[0], parent_path, ns)
            return None

        full_path = f"{parent_path}/{tag_name}" if parent_path else tag_name

        # Зберігаємо інформацію про елемент
        element_info = {
            'name': tag_name,
            'minOccurs': element.get('minOccurs', '1'),
            'maxOccurs': element.get('maxOccurs', '1'),
            'children': []
            # 'type': None # Додамо пізніше
        }

        # Описи та короткі назви
        annotation = element.find('xsd:annotation', ns)
        if annotation is not None:
            doc = annotation.find('xsd:documentation', ns)
            if doc is not None and doc.text:
                self.xsd_descriptions[full_path] = doc.text.strip()
            appinfo = annotation.find('xsd:appinfo', ns)
            if appinfo is not None and appinfo.text:
                self.xsd_appinfo[full_path] = appinfo.text.strip()

        # Обробка complexType
        complex_type = element.find('xsd:complexType', ns)
        type_name = element.get('type')

        if complex_type is None and type_name and not type_name.startswith('xsd:'):
            # Знаходимо тип за іменем
            complex_type = element.getroottree().xpath(f"//xsd:complexType[@name='{type_name}']", namespaces=ns)
            complex_type = complex_type[0] if complex_type else None

        if complex_type is not None:
            # Обробка xsd:sequence, xsd:choice, xsd:all
            for group_tag in ['sequence', 'choice', 'all']:
                group = complex_type.find(f'xsd:{group_tag}', ns)
                if group is not None:
                    element_info['type'] = group_tag # Зберігаємо тип групи
                    for child_element in group.findall('xsd:element', ns):
                        child_info = self._parse_xsd_element(child_element, full_path, ns)
                        if child_info:
                            element_info['children'].append(child_info)

        self.xsd_schema[full_path] = element_info
        return element_info

    def _add_element_to_tree(self, element, parent_item, full_path=""):
        """ Рекурсивно додає XML-елементи до моделі дерева, встановлюючи підказки.
        """
        name = etree.QName(element).localname
        # #log_msg(logFile, f"name = {name}")
        # Оновлюємо повний шлях
        if full_path:
            full_path = f"{full_path}/{name}"
        else:
            full_path = name

        # Використовуємо українську назву з appinfo, якщо вона є, інакше — технічну назву
        display_name = self.xsd_appinfo.get(full_path, name)

        # Створюємо елементи для моделі
        name_item = QStandardItem(display_name)
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
        
        # Додаємо обов'язкові, але відсутні дочірні елементи
        if full_path in self.xsd_schema:
            schema = self.xsd_schema[full_path]
            existing_children_tags = {child.tag for child in element}

            for child_schema in schema.get('children', []):
                child_tag = child_schema['name']
                if child_tag not in existing_children_tags and child_schema.get('minOccurs', '1') != '0':
                    # Створюємо та додаємо відсутній обов'язковий елемент
                    new_child = etree.SubElement(element, child_tag)
                    new_child.text = " " # Щоб не був самозакриваючим

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
            # Завантажуємо описи XSD, тільки якщо їх ще немає
            if not self.xsd_descriptions and path_to_xsd:
                self.xsd_descriptions = self.load_xsd_descriptions(path_to_xsd)

            if tree is not None:
                self.xml_tree = tree
            elif xml_path:
                self.xml_tree = etree.parse(xml_path)

            # Очищаємо існуючу модель дерева при повторному відкритті XML
            self.model.removeRows(0, self.model.rowCount())

            root = self.xml_tree.getroot()

            # Рекурсивна функція для побудови дерева
            def build_tree(xml_node, parent_qt_item, parent_path=""):
                # Створюємо вузол для поточного елемента
                current_path = f"{parent_path}/{xml_node.tag}" if parent_path else xml_node.tag
                name_item, value_item = self._create_qt_items_for_element(xml_node, current_path)
                parent_qt_item.appendRow([name_item, value_item])

                # Рекурсивно обробляємо дочірні елементи
                for child_xml_node in xml_node:
                    build_tree(child_xml_node, name_item, current_path)

            # Починаємо побудову з кореня
            build_tree(root, self.model.invisibleRootItem())
            
            # Валідація при завантаженні вимкнена для пришвидшення.
            # Вона буде виконуватися вручну через кнопку "Перевірити".
            # self._validate_and_color_tree()

        except Exception as e:
            log_msg(logFile, f"Помилка при завантаженні XML: {e}")


    def _create_qt_items_for_element(self, element, full_path):
        """Створює QStandardItem для елемента та його значення."""
        display_name = self.xsd_appinfo.get(full_path, element.tag)
        description = self.xsd_descriptions.get(full_path, "")

        name_item = QStandardItem(display_name)
        name_item.setEditable(False)
        name_item.setData(full_path, Qt.UserRole)
        if description:
            name_item.setToolTip(description)

        # --- Спеціальна логіка для відображення StateActType ---
        is_state_act_type = full_path.endswith("/StateActInfo/StateActType")
        is_category = full_path.endswith("/CategoryPurposeInfo/Category")
        is_purpose = full_path.endswith("/CategoryPurposeInfo/Purpose")
        is_ownership_code = full_path.endswith("/OwnershipInfo/Code")
        is_doc_code = self.doc_code_delegate._is_target_element(name_item.index())
        is_doc_type = self.doc_type_delegate._is_target_element(name_item.index())
        is_land_code = self.land_code_delegate._is_target_element(name_item.index())
        is_closed = self.closed_delegate._is_target_element(name_item.index())
        value_text = element.text.strip() if element.text and element.text.strip() else ""

        # Замінюємо код на назву для відповідних елементів
        if is_state_act_type:
            value_text = self.state_act_delegate.state_act_types.get(value_text, value_text)
        elif is_category:
            value_text = self.category_delegate.category_types.get(value_text, value_text)
        elif is_purpose:
            value_text = self.purpose_delegate.all_purposes.get(value_text, value_text)
        elif is_ownership_code: # noqa
            value_text = self.ownership_delegate.ownership_forms.get(value_text, value_text)
        elif full_path.endswith("/TechnicalDocumentationInfo/DocumentList"):
            value_text = self.doc_code_delegate.doc_list.get(value_text, value_text)
        elif is_doc_type:
            value_text = self.doc_type_delegate.doc_types.get(value_text, value_text)
        elif is_land_code:
            value_text = self.land_code_delegate.land_codes.get(value_text, value_text)
        elif is_closed:
            value_text = self.closed_delegate.closed_options.get(value_text, value_text)


        value_item = QStandardItem(value_text)

        # Дозволяємо редагування для "листків" (елементів без дочірніх вузлів)
        # або для елементів, які мають порожній текстовий вузол.
        # Або якщо це наш спеціальний елемент
        is_leaf = len(element) == 0

        if is_state_act_type or is_category or is_purpose or is_ownership_code or is_doc_type or is_land_code or is_closed or full_path.endswith("/TechnicalDocumentationInfo/DocumentList"):
            value_item.setEditable(True)
        else:
            value_item.setEditable(is_leaf)

        value_item.setData(full_path, Qt.UserRole)
        if description:
            value_item.setToolTip(description)        

        return name_item, value_item

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
        # #log_msg(logFile) # recursion
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

    def _validate_and_color_tree(self, generate_report=False):
        """
        Рекурсивно обходить дерево, валідує елементи та зафарбовує їх у разі помилки.
        Також може генерувати звіт про помилки.
        """
        default_brush = QBrush(Qt.black)
        error_brush = QBrush(QColor("red"))
        errors = []

        def traverse_and_validate(item):
            """
            Рекурсивна функція. Повертає True, якщо гілка валідна, інакше False.
            """
            path = item.data(Qt.UserRole)
            xml_element = self._find_xml_element_by_path(path)

            # 1. Рекурсивно валідуємо дочірні елементи
            has_invalid_child = False
            for row in range(item.rowCount()):
                child_item = item.child(row, 0)
                if not traverse_and_validate(child_item):
                    has_invalid_child = True

            # 2. Валідуємо значення поточного елемента
            is_self_valid = validate_element(xml_element, path)
            if not is_self_valid and generate_report:
                value = xml_element.text if xml_element is not None else "N/A"
                errors.append(f"Некоректне значення '{value}' для елемента: {path}")

            # 3. Валідуємо структуру (наявність обов'язкових дочірніх елементів)
            is_structure_valid = True
            if path in self.xsd_schema and xml_element is not None:
                schema = self.xsd_schema[path]
                if 'children' in schema:
                    existing_children_tags = {child.tag for child in xml_element}
                    
                    # Перевірка для xsd:choice
                    if schema.get('type') == 'choice' and schema.get('minOccurs', '1') != '0':
                        if not any(child['name'] in existing_children_tags for child in schema.get('children', [])):
                            is_structure_valid = False
                            possible_children = ", ".join([child['name'] for child in schema.get('children', [])])
                            if generate_report:
                                errors.append(f"Відсутній обов'язковий елемент вибору (один з: {possible_children}) в: {path}")
                    else: # Перевірка для xsd:sequence та xsd:all
                        for child_schema in schema.get('children', []):
                            if schema.get('type') != 'choice' and child_schema.get('minOccurs', '1') != '0' and child_schema['name'] not in existing_children_tags:
                                is_structure_valid = False
                                if generate_report:
                                    errors.append(f"Відсутній обов'язковий елемент '{child_schema['name']}' в: {path}")

            # 4. Визначаємо, чи є помилка в поточній гілці
            is_branch_valid = is_self_valid and is_structure_valid and not has_invalid_child

            # 5. Зафарбовуємо елемент
            brush = default_brush if is_branch_valid else error_brush
            item.setForeground(brush)
            value_item = item.parent().child(item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
            if value_item:
                value_item.setForeground(brush)

            return is_branch_valid

        # Запускаємо обхід з кореневого елемента
        root_item = self.model.invisibleRootItem().child(0, 0)
        if root_item:
            traverse_and_validate(root_item)
        
        return errors

    def _generate_ukr_path(self, path_str):
        """Створює читабельний український шлях (хлібні крихти)."""
        if not path_str:
            return ""
        parts = path_str.split('/')
        ukr_parts = []
        for i in range(len(parts)):
            current_sub_path = "/".join(parts[:i+1])
            # Отримуємо українську назву для повного підшляху, або беремо назву тега за замовчуванням
            ukr_name = self.xsd_appinfo.get(current_sub_path, parts[i])
            ukr_parts.append(ukr_name)
        return " -> ".join(ukr_parts)



    def _validate_and_color_tree(self, generate_report=False):
        """
        Рекурсивно обходить дерево, валідує елементи та зафарбовує їх у разі помилки.
        Також може генерувати звіт про помилки.
        """
        default_brush = QBrush(Qt.black)
        error_brush = QBrush(QColor("red"))
        errors = []

        def clear_tooltips(item):
            """Рекурсивно очищує старі помилки з підказок."""
            path = item.data(Qt.UserRole)
            if path in self.xsd_descriptions:
                base_tooltip = self.xsd_descriptions[path]
                item.setToolTip(base_tooltip)
                value_item = item.parent().child(item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
                if value_item:
                    value_item.setToolTip(base_tooltip)
            
            for row in range(item.rowCount()):
                child_item = item.child(row, 0)
                if child_item:
                    clear_tooltips(child_item)

        # Очищуємо старі підказки перед новою валідацією
        root_item_for_clear = self.model.invisibleRootItem().child(0, 0)
        if root_item_for_clear:
            clear_tooltips(root_item_for_clear)

        def generate_ukr_path(path_str):
            """Створює читабельний український шлях (хлібні крихти)."""
            if not path_str:
                return ""
            parts = path_str.split('/')
            ukr_parts = []
            for i in range(len(parts)):
                current_sub_path = "/".join(parts[:i+1])
                # Отримуємо українську назву для повного підшляху, або беремо назву тега за замовчуванням
                ukr_name = self.xsd_appinfo.get(current_sub_path, parts[i])
                ukr_parts.append(ukr_name)
            return " -> ".join(ukr_parts)

        def traverse_and_validate(item):
            """
            Рекурсивна функція. Повертає True, якщо гілка валідна, інакше False.
            """
            path = item.data(Qt.UserRole)
            xml_element = self._find_xml_element_by_path(path)
            direct_item_errors = []  # Помилки безпосередньо цього елемента
            child_errors = []  # Помилки, зібрані з дочірніх елементів

            # 1. Рекурсивно валідуємо дочірні елементи
            has_invalid_child = False
            for row in range(item.rowCount()):
                child_item = item.child(row, 0)
                is_child_branch_valid, collected_child_errors = traverse_and_validate(
                    child_item)
                if not is_child_branch_valid:
                    has_invalid_child = True
                    child_errors.extend(
                        collected_child_errors)  # Збираємо помилки з дочірніх гілок

            # 2. Валідуємо значення поточного елемента
            is_self_valid = validate_element(xml_element, path)
            if not is_self_valid and generate_report:
                ukr_path = self._generate_ukr_path(path)
                # Очищуємо назву елемента від символів меню
                ukr_name = item.text().rstrip(" ⋮↵")
                value = xml_element.text if xml_element is not None else "N/A"
                # Формуємо повідомлення про некоректне значення
                error_msg = f"В елементі '{ukr_name}' некоректне значення: '{value}'"
                direct_item_errors.append(error_msg)
                # Додаємо до загального звіту
                errors.append(error_msg)

            # 3. Валідуємо структуру (наявність обов'язкових дочірніх елементів)
            is_structure_valid = True
            # Використовуємо український шлях для повідомлень про структурні помилки
            ukr_path_for_structure = self._generate_ukr_path(path)
            if path in self.xsd_schema and xml_element is not None:
                schema = self.xsd_schema[path]
                if 'children' in schema:
                    existing_children_tags = {child.tag for child in xml_element}

                    # Перевірка для xsd:choice
                    if schema.get('type') == 'choice' and schema.get('minOccurs', '1') != '0':
                        if not any(child['name'] in existing_children_tags for child in schema.get('children', [])):
                            is_structure_valid = False
                            possible_children_ukr = ", ".join([
                                self.xsd_appinfo.get(
                                    f"{path}/{child['name']}", child['name'])
                                for child in schema.get('children', [])
                            ]).rstrip(" ⋮↵")
                            if generate_report:
                                error_msg = f"В елементі '{item.text().rstrip(' ⋮↵')}' відсутній один з піделементів: {possible_children_ukr}"
                                direct_item_errors.append(error_msg)
                                # Додаємо до загального звіту
                                errors.append(error_msg)
                    else:  # Перевірка для xsd:sequence та xsd:all
                        for child_schema in schema.get('children', []):
                            if schema.get('type') != 'choice' and child_schema.get('minOccurs', '1') != '0' and child_schema['name'] not in existing_children_tags:
                                is_structure_valid = False
                                if generate_report:
                                    # Отримуємо українську назву для відсутнього дочірнього елемента
                                    child_ukr_name = self.xsd_appinfo.get(f"{path}/{child_schema['name']}", child_schema['name']).rstrip(" ⋮↵")
                                    parent_ukr_name = item.text().rstrip(" ⋮↵")
                                    
                                    error_msg = f"В елементі '{parent_ukr_name}' відсутній піделемент '{child_ukr_name}'"
                                    direct_item_errors.append(error_msg)
                                    # Додаємо до загального звіту
                                    errors.append(error_msg)

            # 4. Визначаємо, чи є помилка в поточній гілці
            is_branch_valid = is_self_valid and is_structure_valid and not has_invalid_child

            # 5. Зафарбовуємо елемент
            has_direct_error = not is_self_valid or not is_structure_valid
            
            # --- Початок змін: Безпечне оновлення кольору ---
            # Використовуємо setData з роллю ForegroundRole, щоб уникнути рекурсивного виклику itemChanged
            brush_to_set = error_brush if has_direct_error else default_brush
            item.model().setData(item.index(), brush_to_set, Qt.ForegroundRole)
            value_item = item.parent().child(
                item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
            if value_item:
                value_item.model().setData(value_item.index(), brush_to_set, Qt.ForegroundRole)
            # --- Кінець змін ---

            # --- Початок змін: Розкриття дерева до елемента з помилкою ---
            if has_direct_error:
                parent = item.parent()
                while parent and parent.index().isValid():
                    self.expand(parent.index())
                    parent = parent.parent()
            # --- Кінець змін ---

            # 6. Оновлюємо підказку
            base_tooltip = self.xsd_descriptions.get(path, "")
            value_item = item.parent().child(
                item.row(), 1) if item.parent() else self.model.item(item.row(), 1)

            # Визначаємо, які помилки показувати в підказці
            tooltip_errors = []
            tooltip_header = "ПОМИЛКИ:"

            if direct_item_errors:
                # Якщо є прямі помилки, показуємо їх
                tooltip_errors = direct_item_errors

            # --- Початок змін: Зберігання помилок для контекстного меню ---
            if direct_item_errors:
                self.validation_errors[path] = direct_item_errors
            # --- Кінець змін ---

            if tooltip_errors:
                error_tooltip_part = f"\n\n{tooltip_header}\n- " + \
                    "\n- ".join(tooltip_errors)
                item.setToolTip(base_tooltip + error_tooltip_part)
                if value_item:
                    value_item.setToolTip(base_tooltip + error_tooltip_part)

            # Повертаємо валідність гілки та список ПРЯМИХ помилок для батьківського елемента
            # Це важливо, щоб батьківський елемент показував помилки своїх дітей, а не помилки "онуків"
            return is_branch_valid, direct_item_errors

        # Запускаємо обхід з кореневого елемента
        root_item = self.model.invisibleRootItem().child(0, 0)
        if root_item:
            traverse_and_validate(root_item)
        
        return errors
