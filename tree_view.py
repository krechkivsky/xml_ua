"""Обробка XML дерева"""

import configparser
import os
import re
import uuid

from lxml import etree
from qgis.PyQt.QtCore import QDate, QModelIndex, Qt, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAction,
    QDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QStyle,
    QTreeView,
)

from .common import config, connector, log_calls, log_msg, logFile
from .date_dialog import DateInputDialog
from .delegates import (
    CategoryDelegate,
    CitizenshipDelegate,
    ClosedDelegate,
    DispatcherDelegate,
    DocumentationTypeDelegate,
    DocumentCodeDelegate,
    LandCodeDelegate,
    OwnershipCodeDelegate,
    ProprietorCodeDelegate,
    PurposeDelegate,
    RegionDelegate,
    StateActTypeDelegate,
)
from .validators import validate_element

CONTAINER_TAGS_TO_DELETE_LAYER = [
    "Leases", "Subleases", "Restrictions", "LandsParcel", "AdjacentUnits"
]

INFO_TAGS_TO_DELETE_FEATURE = [
    "LeaseInfo", "SubleaseInfo", "RestrictionInfo", "LandParcelInfo", "AdjacentUnitInfo"
]

PROTECTED_TAGS = [
    "ParcelMetricInfo",  # Ділянка
    "CadastralQuarterInfo",  # Квартал
    "CadastralZoneInfo",  # Зона
    "Polyline",  # Полілінії
    "PointInfo"  # Вузли
]


class CustomTreeView(QTreeView):

    """ 
        Клас віджета XML дерева
    """

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
        self.validation_errors = {}  # Словник для зберігання помилок валідації

        self.tree_row = 0

        self.model = QStandardItemModel()
        self.setModel(self.model)

        self.model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        connector.connect(self.model, "itemChanged",
                          self.on_tree_model_data_changed)
        self.group_name = ""

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            self.show_tree_view_context_menu)




        self.allowed_dothers = {}
        self.load_allowed_dothers()
        self.elements_to_expand = config.get(
            "ElementsToExpand", "expanded").split(", ")

        self.state_act_delegate = StateActTypeDelegate(self)
        self.category_delegate = CategoryDelegate(self)
        self.purpose_delegate = PurposeDelegate(self)
        self.ownership_delegate = OwnershipCodeDelegate(self)
        self.doc_code_delegate = DocumentCodeDelegate(self)
        self.doc_type_delegate = DocumentationTypeDelegate(self)
        self.land_code_delegate = LandCodeDelegate(self)
        self.closed_delegate = ClosedDelegate(self)
        self.citizenship_delegate = CitizenshipDelegate(self)
        self.region_delegate = RegionDelegate(self)
        self.proprietor_code_delegate = ProprietorCodeDelegate(self)

        self.dispatcher_delegate = DispatcherDelegate(
            parent=self,
            state_act_delegate=self.state_act_delegate,
            category_delegate=self.category_delegate,
            purpose_delegate=self.purpose_delegate,
            ownership_delegate=self.ownership_delegate,
            doc_code_delegate=self.doc_code_delegate,
            doc_type_delegate=self.doc_type_delegate,
            land_code_delegate=self.land_code_delegate,
            closed_delegate=self.closed_delegate,
            citizenship_delegate=self.citizenship_delegate,
            region_delegate=self.region_delegate,
            proprietor_code_delegate=self.proprietor_code_delegate
        )

        self.doc_type_delegate.documentationTypeChanged.connect(
            self.on_documentation_type_changed)

        self.setItemDelegateForColumn(1, self.dispatcher_delegate)

        self.load_restrictions_data()

    def mouseDoubleClickEvent(self, event):
        """
        Intercepts double-clicks to open dedicated selection dialogs for some
        fixed-list elements (e.g. land category) and prevents inline editors.
        Falls back to the default behavior for regular elements.
        """
        try:
            index = self.indexAt(event.pos())
            if index.isValid() and index.column() == 1:
                handled = bool(self.on_double_click(index))
                if handled:
                    event.accept()
                    return
        except Exception:
            pass
        super().mouseDoubleClickEvent(event)

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

        if self.tree_upd:
            return



        if item is None or item.column() != 1:
            return

        self.tree_upd = True
        try:

            index = item.index()

            name_item_index = index.sibling(index.row(), 0)

            full_path = self.model.data(name_item_index, Qt.ItemDataRole.UserRole)
            xml_element = self.model.data(name_item_index, Qt.ItemDataRole.UserRole + 10)

            value = self.model.data(index, Qt.ItemDataRole.EditRole)

            if not full_path:
                log_msg(
                    logFile, "ПОМИЛКА: Не вдалося отримати шлях для зміненого елемента.")
                return

            self.update_xml_tree(full_path, value, xml_element)

            self.mark_as_changed()  # Це оновить заголовок вкладки

            self.dataChangedInTree.emit(full_path, value)

        finally:

            self.tree_upd = False

    def update_xml_tree(self, full_path, value, xml_element=None):
        """
        Оновлює self.xml_tree на основі full_path та value.
        """

        if self.xml_tree is None:

            return

        try:


            if xml_element is not None:
                xml_element.text = str(value) if value is not None else ""
                return

            xpath_expression = f"/{full_path}"
            elements = self.xml_tree.xpath(xpath_expression)

            if elements:
                element_to_update = elements[0]
                element_to_update.text = str(value) if value is not None else ""
            else:
                log_msg(
                    logFile, f"ПОМИЛКА ЗБЕРЕЖЕННЯ: Елемент за шляхом '{xpath_expression}' не знайдено в XML-дереві.")
        except Exception as e:
            log_msg(logFile, f"Критична помилка при оновленні XML-дерева: {e}")

    def load_restrictions_data(self):
        """Завантажує та структурує дані з restrictions.csv."""

        restrictions_path = os.path.join(os.path.dirname(
            __file__), 'templates', 'restriction.ini')
        if not os.path.exists(restrictions_path):
            log_msg(
                logFile, f"Файл з обмеженнями не знайдено: {restrictions_path}")
            return

        try:
            config = configparser.ConfigParser()

            config.read(restrictions_path, encoding='utf-8')

            if 'RestrictionCode' in config:
                all_codes = dict(config['RestrictionCode'])

                self.restrictions_all_codes = dict(all_codes)
                for code, name in all_codes.items():

                    section_code = code.split('.')[0]
                    if len(section_code) > 2:  # для кодів типу '01', '02'
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
        select_code_action.triggered.connect(
            lambda: self.select_restriction_code(item))
        menu.addAction(select_code_action)
        menu.exec(self.viewport().mapToGlobal(point))

    def get_key_item_path(self, item):
        """Отримує шлях до елемента в дереві"""

        path = []
        while item:
            path.insert(0, item.text())
            item = item.parent()
        return "/".join(path)

    def editNode(self, item):
        """ Викликається, коли вузол дерева редагується.
        """

        full_path = self.get_full_path(item)
        value = item.text()

        self.dataChangedInTree.emit(full_path, value)
        return

    def load_allowed_dothers(self):  # after icon click
        """ 
            Завантаження списків дозволених дочірніх елементів

            Списки дозволених дочірніх елементів описуються в ini.
            Оскільки, не всім елементам дерева можна додавати дочірні.

        """

        if "AllowedDothers" in config:
            for path, rules in config["AllowedDothers"].items():
                self.allowed_dothers[path.strip()] = {}

                rules = " ".join(rules.split())
                elements = rules.split(" ")
                for i in range(0, len(elements), 2):
                    try:
                        element = elements[i]

                        limit = int(elements[i + 1])
                        self.allowed_dothers[path.strip()][element] = limit
                    except (IndexError, ValueError):
                        log_msg(
                            logFile, f"Помилка у секції [AllowedDothers] для шляху '{path.strip()}': {rules}")  # pylint: disable=line-too-long

    def show_tree_view_context_menu(self, point):
        """
        Створює та показує контекстне меню для елемента XML-дерева у віджеті CustomTreeView.
        """
        index = self.indexAt(point)
        if not index.isValid():
            return

        if not index.parent().isValid():

            if not self.parent.current_xml:
                return

            menu = QMenu()

            save_action = QAction(
                self.parent.plugin.action_save_tool.icon(), "Зберегти", self)
            save_as_template_action = QAction(
                self.parent.plugin.action_save_as_template_tool.icon(), "Зберегти як шаблон...", self)

            menu.addAction(save_action)
            menu.addAction(save_as_template_action)

            close_action = QAction(self.style().standardIcon(
                QStyle.StandardPixmap.SP_DialogCloseButton), "Закрити", self)
            close_action.triggered.connect(
                lambda: self.parent.process_action_close_xml(self.parent.current_xml))
            menu.addAction(close_action)

            menu.addSeparator()

            menu.exec(self.viewport().mapToGlobal(point))
            return

        item = self.model.itemFromIndex(index)
        parent_item = item.parent()  # Визначаємо parent_item тут

        full_item_path = item.data(Qt.ItemDataRole.UserRole)

        schema_item_path = re.sub(
            r'\[\d+\]', '', full_item_path) if full_item_path else ""

        menu = QMenu()
        has_actions = False

        coordinate_system_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/CoordinateSystem"
        if schema_item_path == coordinate_system_path:
            menu = QMenu()
            has_actions = False

            if item.hasChildren():

                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(
                        f"Видалити систему координат '{child_item.text()}'", self)

                    delete_action.triggered.connect(
                        lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions:
                menu.exec(self.viewport().mapToGlobal(point))
                return

        height_system_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/HeightSystem"
        if schema_item_path == height_system_path:
            menu = QMenu()
            has_actions = False

            if item.hasChildren():

                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(
                        f"Видалити систему висот '{child_item.text()}'", self)

                    delete_action.triggered.connect(
                        lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions:
                menu.exec(self.viewport().mapToGlobal(point))
                return

        measurement_unit_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/MeasurementUnit"
        if schema_item_path == measurement_unit_path:
            menu = QMenu()
            has_actions = False

            if item.hasChildren():

                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(
                        f"Видалити одиницю виміру '{child_item.text()}'", self)

                    delete_action.triggered.connect(
                        lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions:
                menu.exec(self.viewport().mapToGlobal(point))
                return

        parcel_location_path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/ParcelLocation"
        if schema_item_path == parcel_location_path:
            menu = QMenu()
            has_actions = False

            if item.hasChildren():

                child_item = item.child(0, 0)
                if child_item:
                    delete_action = QAction(
                        f"Видалити місцезнаходження '{child_item.text()}'", self)

                    delete_action.triggered.connect(
                        lambda _, it=child_item: self.delete_element(it))
                    menu.addAction(delete_action)
                    has_actions = True

            if has_actions:
                menu.exec(self.viewport().mapToGlobal(point))
                return

        if schema_item_path in self.xsd_schema:
            element_schema = self.xsd_schema[schema_item_path]
            xml_element = self._find_xml_element_by_path(full_item_path)

            if xml_element is not None and 'children' in element_schema:
                add_menu = QMenu("Додати", self)
                added_to_add_menu = False
                for child_info in element_schema['children']:
                    child_tag = child_info['name']
                    max_occurs = child_info.get('maxOccurs', 1)

                    current_count = len(xml_element.findall(child_tag))

                    if max_occurs == 'unbounded' or current_count < int(max_occurs):

                        if element_schema.get('type') == 'choice':

                            choice_children_exist = any(len(xml_element.findall(
                                c['name'])) > 0 for c in element_schema['children'])
                            if not choice_children_exist:
                                add_action = QAction(
                                    "Додати елемент вибору...", self)
                                add_action.triggered.connect(
                                    lambda _, p_item=item, schema=element_schema: self.handle_add_choice_element(
                                        p_item, schema)
                                )
                                add_menu.addAction(add_action)
                                added_to_add_menu = True

                                break
                        else:

                            child_ukr_name = self.xsd_appinfo.get(
                                f"{schema_item_path}/{child_tag}", child_tag)
                            add_action = QAction(f"{child_ukr_name}", self)
                            add_action.triggered.connect(
                                lambda _, p_item=item, c_tag=child_tag: self.add_child_element(
                                    p_item, c_tag)
                            )
                            add_menu.addAction(add_action)
                            added_to_add_menu = True

                if added_to_add_menu:

                    if has_actions and not menu.actions()[-1].isSeparator():
                        menu.addSeparator()
                    menu.addMenu(add_menu)
                    has_actions = True

        adjacent_unit_info_path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/AdjacentUnits/AdjacentUnitInfo"
        if schema_item_path == adjacent_unit_info_path:
            log_msg(logFile, f"Додавання пункту інвертування для елемента")
            invert_action = QAction("Інвертувати лінії суміжника", self)
            invert_action.triggered.connect(
                lambda: self.invert_lines_for_adjacent(item))
            menu.addAction(invert_action)
            has_actions = True

        if parent_item:  # Не дозволяємо видаляти кореневий елемент
            if has_actions and not menu.actions()[-1].isSeparator():
                menu.addSeparator()
            item_text = item.text() if item else ""
            delete_action = QAction(f"Видалити '{item_text}'", self)
            delete_action.triggered.connect(
                lambda _, it=item: self.delete_element(it))
            menu.addAction(delete_action)
            has_actions = True

        if has_actions:
            menu.exec(self.viewport().mapToGlobal(point))

    def invert_lines_for_adjacent(self, item):
        """Інвертує порядок ліній у елементі AdjacentUnitInfo."""
        full_item_path = item.data(Qt.ItemDataRole.UserRole)
        xml_element = self._find_xml_element_by_path(full_item_path)

        if xml_element is not None:
            lines = xml_element.findall("Line")
            if len(lines) < 2:
                QMessageBox.information(
                    self, "Інформація", "Недостатньо ліній для інвертування.")
                return

            for line in lines:
                xml_element.remove(line)
            for line in reversed(lines):
                xml_element.append(line)

            self.update_view_from_tree()
            self.mark_as_changed()
            QMessageBox.information(
                self, "Успіх", "Порядок ліній успішно інвертовано.")
        else:
            QMessageBox.warning(
                self, "Помилка", "Не вдалося знайти елемент для інвертування.")

    def show_item_error_dialog(self, item_path):
        """Показує діалогове вікно з помилками для конкретного елемента."""

        if item_path in self.validation_errors:
            errors = self.validation_errors[item_path]
            error_text = "\n- ".join(errors)

            ukr_path = self._generate_ukr_path(item_path)

            QMessageBox.warning(self,
                                f"Помилки в елементі",
                                f"Для елемента:\n<b>{ukr_path}</b>\n\nЗнайдено наступні помилки:\n- {error_text}")

    def mark_as_changed(self):
        """Позначає поточний XML-файл як змінений."""

        if self.parent and hasattr(self.parent, 'mark_as_changed'):
            self.parent.mark_as_changed()

    def get_expanded_indexes(self, index, expanded_list):
        """
        Рекурсивно збирає шляхи розкритих елементів.
        """
        if self.isExpanded(index):
            item = self.model.itemFromIndex(index)
            if item:

                path = item.data(Qt.ItemDataRole.UserRole)
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
                    path = item.data(Qt.ItemDataRole.UserRole)
                    if path in expanded_list:
                        self.expand(index)

                    if self.model.hasChildren(index):
                        find_and_expand(index)

        find_and_expand(self.model.invisibleRootItem().index())

    def update_view_from_tree(self):
        """
        Примусово оновлює відображення дерева на основі поточного стану self.xml_tree.
        """

        if self.xml_tree is None:
            return

        def update_items(parent_item):
            for row in range(parent_item.rowCount()):
                name_item = parent_item.child(row, 0)
                value_item = parent_item.child(row, 1)
                if name_item and value_item:
                    full_path = name_item.data(Qt.ItemDataRole.UserRole)
                    if full_path:

                        xml_element = self._find_xml_element_by_path(full_path)
                        if xml_element is not None:
                            new_value = xml_element.text.strip() if xml_element.text else ""
                            if value_item.text() != new_value:
                                value_item.setText(new_value)

                    if name_item.hasChildren():
                        update_items(name_item)

        update_items(self.model.invisibleRootItem())

    def select_restriction_code(self, item):
        """Запускає двокроковий діалог вибору коду обмеження."""
        if not self.restrictions_data:
            QMessageBox.warning(
                self, "Помилка", "Дані про обмеження не завантажено.")
            return

        main_codes = {code: name for section in self.restrictions_data.values(
        ) for code, name in section.items() if len(code) == 2}
        main_code_display_names = sorted(
            [f"{code} - {name}" for code, name in main_codes.items()])

        dialog1 = QInputDialog(self)
        dialog1.setFixedWidth(800)
        dialog1.setLabelText("Виберіть розділ:")
        dialog1.setComboBoxItems(main_code_display_names)
        dialog1.setWindowTitle("Вибір розділу обмеження")
        ok = dialog1.exec()
        main_code_selection = dialog1.textValue()

        if not ok or not main_code_selection:
            return

        selected_main_code = main_code_selection.split(' - ')[0]
        selected_code = selected_main_code

        sub_codes_exist = any(
            str(code).startswith(selected_main_code + ".")
            for section in self.restrictions_data.values()
            for code in section
        )

        if sub_codes_exist:

            sub_codes = {}
            if selected_main_code in self.restrictions_data:
                sub_codes = {code: name for code, name in self.restrictions_data[selected_main_code].items(
                ) if code.startswith(selected_main_code + '.')}

            if sub_codes:

                sub_codes[selected_main_code] = main_codes[selected_main_code]

                sub_code_display_names = sorted(
                    [f"{code} - {name}" for code, name in sub_codes.items()])

                dialog2 = QInputDialog(self)
                dialog2.setFixedWidth(800)
                dialog2.setLabelText("Виберіть код:")
                dialog2.setComboBoxItems(sub_code_display_names)
                dialog2.setWindowTitle("Уточнення коду обмеження")
                ok = dialog2.exec()
                sub_code_selection = dialog2.textValue()

                if ok and sub_code_selection:
                    selected_code = sub_code_selection.split(' - ')[0]
                elif not ok:  # Якщо користувач натиснув "Скасувати" на другому етапі
                    return

        selected_name = ""
        for section in self.restrictions_data.values():
            if selected_code in section:
                selected_name = section[selected_code]
                break


        item.setText(selected_code)
        try:
            item.setData(selected_code, Qt.ItemDataRole.EditRole)
        except Exception:
            pass
        try:
            if selected_name:
                item.setToolTip(str(selected_name))
        except Exception:
            pass

        if item.parent():

            restriction_info_item = item.parent()
            if restriction_info_item:

                for row in range(restriction_info_item.rowCount()):
                    child_name_item = restriction_info_item.child(row, 0)
                    if child_name_item and child_name_item.text() == self.xsd_appinfo.get(f"{restriction_info_item.data(Qt.ItemDataRole.UserRole)}/RestrictionName", "RestrictionName"):

                        restriction_name_value_item = restriction_info_item.child(
                            row, 1)
                        if restriction_name_value_item:
                            restriction_name_value_item.setText(selected_name)
                        break

    def on_double_click(self, index):
        """
        Обробляє подвійний клік на значенні (2-а колонка).

        Returns:
            bool: True if handled here (and default double-click behavior should be suppressed).
        """
        if not index.isValid() or index.column() != 1:
            return False

        item = self.model.itemFromIndex(index)
        if not item:
            return False

        full_item_path = item.data(Qt.ItemDataRole.UserRole)
        schema_item_path = re.sub(
            r'\[\d+\]', '', full_item_path) if full_item_path else ""

        if schema_item_path and schema_item_path.endswith("Date"):
            self.handle_date_edit(item)
            return True
        elif schema_item_path and schema_item_path.endswith("/FileID/FileGUID"):

            new_guid = str(uuid.uuid4()).upper()

            reply = QMessageBox.question(self, 'Перегенерація GUID',
                                         f"Згенерувати новий унікальний ідентифікатор файлу?\n\nНовий GUID: {new_guid}",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:

                item.setText(new_guid)
                return True
            return True
        elif schema_item_path and schema_item_path.endswith("/ParcelLocationInfo/Region"):

            self.handle_region_edit(item)
            return True
        elif schema_item_path and schema_item_path.endswith("/CategoryPurposeInfo/Category"):
            self.handle_land_category_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/CategoryPurposeInfo/Purpose"):
            self.handle_land_purpose_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/OwnershipInfo/Code"):
            self.handle_ownership_code_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/TechnicalDocumentationInfo/DocumentationType"):
            self.handle_documentation_type_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("DocumentList"):
            self.handle_document_list_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/LandParcelInfo/LandCode"):
            self.handle_land_parcel_land_code_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/StateActInfo/StateActType"):
            self.handle_state_act_type_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/StateActInfo/EntitlementDocument/Document"):
            self.handle_reason_act_doc_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/RestrictionInfo/RestrictionCode"):
            self.select_restriction_code(item)
            return True

        elif schema_item_path and (
            schema_item_path.endswith("/NaturalPerson/Citizenship") or
            schema_item_path.endswith("/Address/Country")            
            ):
            self.handle_citizenship_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/Address/Region"):
            self.handle_region_edit(index)
            return True
        elif schema_item_path and schema_item_path.endswith("/ProprietorInfo/ProprietorCode"):
            self.handle_proprietor_code_edit(index)
            return True


        return False

    def handle_land_category_edit(self, index: QModelIndex):
        """
        Opens a combo dialog for land category selection.
        """
        categories = getattr(self.category_delegate, "category_types", {}) or {}
        if not categories:
            QMessageBox.warning(
                self, "Помилка", "Секція [LandCategories] не знайдена або порожня у файлі конфігурації.")
            return


        def _key_sort(k: str):
            try:
                return (0, int(str(k).strip()))
            except Exception:
                return (1, str(k))

        items = [(k, categories[k]) for k in sorted(categories.keys(), key=_key_sort)]
        display_names = [v for _, v in items]

        current_code = self.model.data(index, Qt.ItemDataRole.EditRole)
        current_name = categories.get(str(current_code), "")
        default_idx = 0
        if current_name:
            try:
                default_idx = display_names.index(current_name)
            except ValueError:
                default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Категорія земель",
            "Виберіть категорію:",
            display_names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        selected_code = None
        try:

            selected_code = self.category_delegate.reverse_category_types.get(selection)
        except Exception:
            selected_code = None
        if not selected_code:
            for k, v in items:
                if v == selection:
                    selected_code = k
                    break
        if not selected_code:
            return


        self.model.setData(index, str(selected_code), Qt.ItemDataRole.EditRole)
        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setToolTip(str(selection))
        except Exception:
            pass

    def handle_land_purpose_edit(self, index: QModelIndex):
        """
        Two-step selection for land purpose (цільове призначення).
        """
        chapters = getattr(self.purpose_delegate, "chapters", {}) or {}
        subchapters = getattr(self.purpose_delegate, "subchapters", {}) or {}
        if not chapters or not subchapters:
            QMessageBox.warning(
                self,
                "Помилка",
                "Секції [LandPurposeChapters]/[LandPurposeSubchapters] не знайдені або порожні у файлі конфігурації.",
            )
            return


        def _key_sort(k: str):
            try:
                return (0, float(str(k).strip()))
            except Exception:
                return (1, str(k))

        chapter_items = [(k, chapters[k]) for k in sorted(chapters.keys(), key=_key_sort)]
        chapter_names = [v for _, v in chapter_items]
        chapter_reverse = {}
        for k, v in chapter_items:
            chapter_reverse.setdefault(v, k)

        chapter_sel, ok1 = QInputDialog.getItem(
            self,
            "Вибір цільового призначення (Крок 1/2)",
            "Виберіть розділ:",
            chapter_names,
            0,
            False,
        )
        if not ok1 or not chapter_sel:
            return

        chapter_code = chapter_reverse.get(chapter_sel)
        if not chapter_code:
            return

        filtered = [(k, v) for k, v in subchapters.items() if str(k).startswith(str(chapter_code) + ".")]
        if not filtered:
            QMessageBox.information(self, "Інформація", "Для вибраного розділу немає підрозділів.")
            return

        filtered.sort(key=lambda kv: kv[0])
        sub_names = [v for _, v in filtered]
        sub_reverse = {}
        for k, v in filtered:
            sub_reverse.setdefault(v, k)

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        default_idx = 0
        if current_code:
            for i, (k, _) in enumerate(filtered):
                if str(k) == current_code:
                    default_idx = i
                    break

        sub_sel, ok2 = QInputDialog.getItem(
            self,
            "Вибір цільового призначення (Крок 2/2)",
            "Виберіть підрозділ:",
            sub_names,
            default_idx,
            False,
        )
        if not ok2 or not sub_sel:
            return

        sub_code = sub_reverse.get(sub_sel)
        if not sub_code:
            return

        self.model.setData(index, str(sub_code), Qt.ItemDataRole.EditRole)
        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setToolTip(str(sub_sel))
        except Exception:
            pass

    def handle_ownership_code_edit(self, index: QModelIndex):
        """
        Opens a combo dialog for ownership form selection.
        """
        forms = getattr(self.ownership_delegate, "ownership_forms", {}) or {}
        if not forms:
            QMessageBox.warning(
                self, "Помилка", "Секція [OwnershipForms] не знайдена або порожня у файлі конфігурації."
            )
            return

        def _key_sort(k: str):
            try:
                return (0, int(str(k).strip()))
            except Exception:
                return (1, str(k))

        items = [(k, forms[k]) for k in sorted(forms.keys(), key=_key_sort)]
        names = [v for _, v in items]

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        default_idx = 0
        if current_code:
            current_name = forms.get(current_code, "")
            if current_name:
                try:
                    default_idx = names.index(current_name)
                except ValueError:
                    default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Форма власності",
            "Виберіть форму власності:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        code = None
        try:
            code = self.ownership_delegate.reverse_ownership_forms.get(selection)
        except Exception:
            code = None
        if not code:
            for k, v in items:
                if v == selection:
                    code = k
                    break
        if not code:
            return

        self.model.setData(index, str(code), Qt.ItemDataRole.EditRole)
        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setToolTip(str(selection))
        except Exception:
            pass

    def handle_documentation_type_edit(self, index: QModelIndex):
        """
        Opens a combo dialog for DocumentationType selection.
        """
        doc_types = getattr(self.doc_type_delegate, "doc_types", {}) or {}
        if not doc_types:
            QMessageBox.warning(
                self, "Помилка", "Секція [DocumentationTypes] не знайдена або порожня у файлі docs_list.ini."
            )
            return

        def _key_sort(k: str):
            try:
                return (0, int(str(k).strip()))
            except Exception:
                return (1, str(k))

        items = [(k, doc_types[k]) for k in sorted(doc_types.keys(), key=_key_sort)]
        names = [v for _, v in items]

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        default_idx = 0
        if current_code:
            current_name = doc_types.get(current_code, "")
            if current_name:
                try:
                    default_idx = names.index(current_name)
                except ValueError:
                    default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Вид документації",
            "Виберіть вид документації:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        code = None
        try:
            code = self.doc_type_delegate.reverse_doc_types.get(selection)
        except Exception:
            code = None
        if not code:
            for k, v in items:
                if v == selection:
                    code = k
                    break
        if not code:
            return

        self.model.setData(index, str(code), Qt.ItemDataRole.EditRole)
        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setToolTip(str(selection))
        except Exception:
            pass


        try:
            self.on_documentation_type_changed(str(code), index)
        except Exception:
            pass

    def handle_document_list_edit(self, index: QModelIndex):
        """
        Opens a combo dialog for selecting a document code in TechnicalDocumentationInfo/DocumentList.
        """
        doc_list = getattr(self.doc_code_delegate, "doc_list", {}) or {}
        if not doc_list:
            QMessageBox.warning(
                self, "Помилка", "Секція [DocsList] не знайдена або порожня у файлі docs_list.ini."
            )
            return

        items = [(str(code), str(name)) for code, name in doc_list.items()]
        items.sort(key=lambda kv: kv[0])

        display_items = [f"{code} - {name}" for code, name in items]

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        default_idx = 0
        if current_code:
            for i, (code, _) in enumerate(items):
                if code == current_code:
                    default_idx = i
                    break

        selection, ok = QInputDialog.getItem(
            self,
            "Документ",
            "Виберіть документ:",
            display_items,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        selected_code = selection.split(" - ", 1)[0].strip()
        friendly = doc_list.get(selected_code, "")
        if not selected_code:
            return


        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setText(str(friendly) if friendly else str(selection))
                it.setToolTip(str(friendly) if friendly else str(selection))
                it.setData(str(selected_code), Qt.ItemDataRole.EditRole)
                return
        except Exception:
            pass

        self.model.setData(index, str(selected_code), Qt.ItemDataRole.EditRole)

    def handle_land_parcel_land_code_edit(self, index: QModelIndex):
        """
        Opens a combo dialog for selecting LandParcelInfo/LandCode.
        """
        land_codes = getattr(self.land_code_delegate, "land_codes", {}) or {}
        if not land_codes:
            QMessageBox.warning(
                self, "Помилка", "Секція [LandCodes] не знайдена або порожня у файлі конфігурації."
            )
            return

        def _key_sort(k: str):
            try:
                return (0, int(str(k).strip()))
            except Exception:
                return (1, str(k))

        items = [(k, land_codes[k]) for k in sorted(land_codes.keys(), key=_key_sort)]
        names = [v for _, v in items]

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        current_name = land_codes.get(current_code, "")
        default_idx = 0
        if current_name:
            try:
                default_idx = names.index(current_name)
            except ValueError:
                default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Код угіддя",
            "Виберіть угіддя:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        selected_code = None
        for k, v in items:
            if v == selection:
                selected_code = k
                break
        if not selected_code:
            return


        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setText(str(selected_code))
                it.setToolTip(str(selection))
                it.setData(str(selected_code), Qt.ItemDataRole.EditRole)
                return
        except Exception:
            pass

        self.model.setData(index, str(selected_code), Qt.ItemDataRole.EditRole)

    def handle_state_act_type_edit(self, index: QModelIndex):
        """
        Opens a combo dialog for selecting StateActInfo/StateActType.
        """
        try:
            state_act_types = dict(config["StateActType"]) if "StateActType" in config else {}
        except Exception:
            state_act_types = {}
        if not state_act_types:

            state_act_types = getattr(self.state_act_delegate, "state_act_types", {}) or {}

        if not state_act_types:
            QMessageBox.warning(
                self, "Помилка", "Секція [StateActType] не знайдена або порожня у файлі конфігурації."
            )
            return

        def _key_sort(k: str):
            try:
                return (0, int(str(k).strip()))
            except Exception:
                return (1, str(k))

        items = [(k, state_act_types[k]) for k in sorted(state_act_types.keys(), key=_key_sort)]
        names = [v for _, v in items]

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        current_name = state_act_types.get(current_code, "")
        default_idx = 0
        if current_name:
            try:
                default_idx = names.index(current_name)
            except ValueError:
                default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Тип державного акта",
            "Виберіть тип:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        selected_code = None
        for k, v in items:
            if v == selection:
                selected_code = k
                break
        if not selected_code:
            return

        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setText(str(selected_code))
                it.setToolTip(str(selection))
                it.setData(str(selected_code), Qt.ItemDataRole.EditRole)
                return
        except Exception:
            pass

        self.model.setData(index, str(selected_code), Qt.ItemDataRole.EditRole)

    def handle_reason_act_doc_edit(self, index: QModelIndex):
        """
        Opens a combo dialog for selecting StateActInfo/EntitlementDocument/Document.
        """
        try:
            reasons = dict(config["ReasonActDoc"]) if "ReasonActDoc" in config else {}
        except Exception:
            log_calls(logFile, "Помилка створення словника ReasonActDoc")
            reasons = {}

        if not reasons:
            QMessageBox.warning(
                self, "Помилка", "Секція [ReasonActDoc] не знайдена або порожня у файлі конфігурації."
            )
            return

        items = [(str(k), str(v)) for k, v in reasons.items()]
        items.sort(key=lambda kv: kv[0])
        names = [v for _, v in items]

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        current_name = reasons.get(current_code, "")
        default_idx = 0
        if current_name:
            try:
                default_idx = names.index(current_name)
            except ValueError:
                default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Назва документа (код)",
            "Виберіть документ:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        selected_code = None
        for k, v in items:
            if v == selection:
                selected_code = k
                break
        if not selected_code:
            return

        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setText(str(selected_code))
                it.setToolTip(str(selection))
                it.setData(str(selected_code), Qt.ItemDataRole.EditRole)
                return
        except Exception:
            log_calls(logFile, "Помилка роботи з текстовим полем.")
            pass

        self.model.setData(index, str(selected_code), Qt.ItemDataRole.EditRole)

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

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_date_str = dialog.get_date()

            if new_date_str != current_value:
                item.setText(new_date_str)

    def handle_citizenship_edit(self, index: QModelIndex):
        """
        Відкриває діалог з випадаючим списком для вибору країни (Громадянство / Адреса).
        Порядок країн зберігається таким, як у xml_ua.ini.
        """
        countries = getattr(self.citizenship_delegate, "countries", {}) or {}
        if not countries:
            QMessageBox.warning(
                self, "Помилка", "Секція [Countries] не знайдена або порожня у файлі конфігурації."
            )
            return

        items = list(countries.items())
        names = list(countries.values())

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        default_idx = 0
        if current_code:
            current_name = countries.get(current_code, "")
            if current_name:
                try:
                    default_idx = names.index(current_name)
                except ValueError:
                    default_idx = 0

        # Динамічний заголовок діалогу залежно від шляху елемента
        schema_item_path = index.data(Qt.ItemDataRole.UserRole) or ""
        if schema_item_path.endswith("/Address/Country"):
            dialog_title = "Країна адреси"
        else:
            dialog_title = "Громадянство"

        selection, ok = QInputDialog.getItem(
            self,
            dialog_title,
            "Виберіть країну:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        code = None
        try:
            code = self.citizenship_delegate.reverse_countries.get(selection)
        except Exception:
            code = None

        if not code:
            for k, v in items:
                if v == selection:
                    code = k
                    break
        if not code:
            return

        self.model.setData(index, str(code), Qt.ItemDataRole.EditRole)
        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setToolTip(str(selection))
        except Exception:
            pass

    def handle_region_edit(self, index: QModelIndex):
        """
        Відкриває діалог з випадаючим списком для вибору області (/Address/Region).
        Записує в модель безпосередньо назву області (наприклад, 'Львівська область').
        """
        regions = getattr(self.region_delegate, "regions", {}) or {}
        if not regions:
            QMessageBox.warning(
                self, "Помилка", "Секція [Region] не знайдена або порожня у файлі конфігурації."
            )
            return

        names = list(regions.values())
        current_value = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()

        default_idx = 0
        if current_value and current_value in names:
            try:
                default_idx = names.index(current_value)
            except ValueError:
                default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Область",
            "Виберіть область:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        # У модель зберігаємо безпосередньо обраний текст області
        self.model.setData(index, str(selection), Qt.ItemDataRole.EditRole)
        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setToolTip(str(selection))
        except Exception:
            pass

    def handle_proprietor_code_edit(self, index: QModelIndex):
        """
        Відкриває діалог з випадаючим списком для вибору шифру рядка власника (/ProprietorInfo/ProprietorCode).
        Записує в модель код (ключ з [ProprietorCode]), відображає назву.
        """
        proprietors = getattr(self.proprietor_code_delegate, "proprietor_codes", {}) or {}
        if not proprietors:
            QMessageBox.warning(
                self, "Помилка", "Секція [ProprietorCode] не знайдена або порожня у файлі конфігурації."
            )
            return

        items = list(proprietors.items())
        names = list(proprietors.values())

        current_code = str(self.model.data(index, Qt.ItemDataRole.EditRole) or "").strip()
        default_idx = 0
        if current_code:
            current_name = proprietors.get(current_code, "")
            if current_name:
                try:
                    default_idx = names.index(current_name)
                except ValueError:
                    default_idx = 0

        selection, ok = QInputDialog.getItem(
            self,
            "Шифр рядка власника",
            "Виберіть категорію власника:",
            names,
            default_idx,
            False,
        )
        if not ok or not selection:
            return

        code = None
        try:
            code = self.proprietor_code_delegate.reverse_codes.get(selection)
        except Exception:
            code = None

        if not code:
            for k, v in items:
                if v == selection:
                    code = k
                    break
        if not code:
            return

        self.model.setData(index, str(code), Qt.ItemDataRole.EditRole)
        try:
            it = self.model.itemFromIndex(index)
            if it:
                it.setToolTip(str(selection))
        except Exception:
            pass



    def rebuild_tree_view(self):
        """
        Повністю перебудовує дерево, зберігаючи розкриті вузли.
        Використовується, коли структура XML значно змінюється.
        """
        if self.xml_tree is None:
            return

        expanded_list = []
        self.get_expanded_indexes(self.rootIndex(), expanded_list)

        self.load_xml_to_tree_view(tree=self.xml_tree)

        self.restore_expanded_indexes(expanded_list)

    def add_child_element(self, parent_item, child_tag):
        """Додає дочірній елемент в XML та в дерево GUI."""

        parent_path = parent_item.data(Qt.ItemDataRole.UserRole)
        schema_parent_path = re.sub(
            r'\[\d+\]', '', parent_path) if parent_path else ""

        parent_xml_element = self._find_xml_element_by_path(parent_path)
        if parent_xml_element is None:

            return

        self._create_and_add_element(
            parent_item, parent_xml_element, child_tag, parent_path, schema_parent_path)

    def handle_add_choice_element(self, parent_item, schema):
        """Показує діалог для вибору та додавання елемента з xsd:choice."""
        parent_path = parent_item.data(Qt.ItemDataRole.UserRole)
        schema_parent_path = re.sub(
            r'\[\d+\]', '', parent_path) if parent_path else ""

        choice_options = {}
        for child_info in schema.get('children', []):
            child_tag = child_info['name']
            child_ukr_name = self.xsd_appinfo.get(
                f"{schema_parent_path}/{child_tag}", child_tag)
            choice_options[child_ukr_name] = child_tag

        if not choice_options:
            QMessageBox.warning(
                self, "Помилка", "Не знайдено варіантів для вибору.")
            return

        selected_ukr_name, ok = QInputDialog.getItem(
            self, "Вибір елемента", "Виберіть, який елемент додати:", list(choice_options.keys()), 0, False)

        if ok and selected_ukr_name:
            selected_child_tag = choice_options[selected_ukr_name]
            parent_xml_element = self._find_xml_element_by_path(parent_path)
            if parent_xml_element is not None:
                self._create_and_add_element(
                    parent_item, parent_xml_element, selected_child_tag, parent_path, schema_parent_path)

    def _create_and_add_element(self, parent_item, parent_xml_element, child_tag, parent_path, schema_parent_path):
        """Створює XML та GUI елементи і додає їх до батьківських."""

        new_xml_element = etree.Element(child_tag)
        if child_tag in ("Urban", "Rural"):
            new_xml_element.text = None
        else:
            new_xml_element.text = " "  # Додаємо пробіл, щоб тег не був самозакриваючим
        parent_xml_element.append(new_xml_element)

        new_child_index = len(parent_xml_element.findall(child_tag))
        full_child_path = f"{parent_path}/{child_tag}[{new_child_index}]"
        name_item, value_item = self._create_qt_items_for_element(
            new_xml_element, full_child_path, f"{schema_parent_path}/{child_tag}")

        parent_item.appendRow([name_item, value_item])

        if child_tag in ("Urban", "Rural"):
            value_item.setEditable(False)
        else:
            value_item.setEditable(True)

        self.parent.mark_as_changed()
        self.expand(parent_item.index())
        try:

            self.dataChangedInTree.emit(full_child_path, new_xml_element.text or "")
        except Exception:
            pass

    def delete_element(self, item):
        """Видаляє елемент з XML та з дерева GUI."""
        item_path = item.data(Qt.ItemDataRole.UserRole)
        xml_element_to_delete = self._find_xml_element_by_path(item_path)

        if xml_element_to_delete is None:
            log_msg(
                logFile, f"Не вдалося знайти XML елемент для видалення: {item_path}")
            return

        parent_xml_element = xml_element_to_delete.getparent()
        if parent_xml_element is None:
            log_msg(
                logFile, f"Не вдалося видалити елемент без батька: {item_path}")
            return

        item_tag = xml_element_to_delete.tag

        if item_tag in PROTECTED_TAGS:
            QMessageBox.warning(self, "Видалення заборонено",
                                f"Видалення елемента '{item.text()}' та відповідного йому шару заборонено.")

            return

        schema_parent_path = re.sub(
            r'\[\d+\]', '', item_path.rsplit('/', 1)[0]) if '/' in item_path else ""
        if schema_parent_path in self.xsd_schema:
            parent_schema = self.xsd_schema[schema_parent_path]
            for child_info in parent_schema.get('children', []):
                if child_info['name'] == item_tag:
                    min_occurs = child_info.get('minOccurs', '1')
                    current_count = len(parent_xml_element.findall(item_tag))
                    if min_occurs == '1' and current_count == 1:
                        reply = QMessageBox.question(self, 'Підтвердження видалення',
                                                     f"Ви намагаєтеся видалити обов'язковий єдиний елемент '{item.text()}'.\n\n"
                                                     "Це може призвести до невідповідності файлу схемі XSD. "
                                                     "Ви впевнені, що хочете продовжити?",
                                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                        if reply == QMessageBox.StandardButton.No:
                            log_msg(
                                logFile, f"Видалення обов'язкового елемента '{item.text()}' скасовано користувачем.")
                            return  # Скасовуємо видалення
                        else:
                            pass  # Продовжуємо, якщо користувач погодився
                    break

        if item_tag in CONTAINER_TAGS_TO_DELETE_LAYER:

            self.parent.delete_xml_section_from_layer_tree(
                item_tag, self.parent.current_xml.group_name)
        elif item_tag in INFO_TAGS_TO_DELETE_FEATURE:

            layer_name = self.parent.XML_INFO_TAG_TO_LAYER_NAME.get(item_tag)
            if layer_name:
                self.parent.delete_qgis_feature_from_xml_element(
                    xml_element_to_delete, layer_name)

                try:
                    parent_xml_element.remove(xml_element_to_delete)
                except ValueError as e:
                    log_msg(
                        logFile, f"Перехоплено очікувану помилку при видаленні вузла з XML: {e}")

                from .topology import GeometryProcessor
                processor = GeometryProcessor(
                    self.parent.current_xml.tree)  # type: ignore
                processor.cleanup_and_renumber_geometry()

                self.parent.current_xml.tree_view.rebuild_tree_view()

            else:
                log_msg(
                    logFile, f"Не знайдено відповідної назви шару для тегу '{item_tag}'. Видалення лише з XML.")
                parent_xml_element.remove(xml_element_to_delete)
                self.parent.current_xml.tree_view.rebuild_tree_view()
                from .topology import GeometryProcessor
                processor = GeometryProcessor(
                    self.parent.current_xml.tree)  # type: ignore
                processor.cleanup_and_renumber_geometry()
        else:

            try:
                parent_xml_element.remove(xml_element_to_delete)
            except ValueError as e:  # Catch if element was already removed by cleanup_geometry
                log_msg(
                    logFile, f"Перехоплено очікувану помилку при видаленні вузла з XML: {e}")
            self.parent.current_xml.tree_view.rebuild_tree_view()
            from .topology import GeometryProcessor
            processor = GeometryProcessor(
                self.parent.current_xml.tree)  # type: ignore
            processor.cleanup_and_renumber_geometry()

        self.parent.mark_as_changed()
        try:

            self.dataChangedInTree.emit(item_path, "")
        except Exception:
            pass

    def _find_xml_element_by_path(self, path):
        """Знаходить елемент в self.xml_tree за XPath."""
        if self.xml_tree is None:
            return None
        if not path:
            return None

        root = self.xml_tree.getroot()

        if hasattr(root, 'xpath'):
            elements = root.xpath(f"/{path}")  # noqa
            return elements[0] if elements else None
        else:  # Fallback для стандартного xml.etree
            return root.find(path)

    def get_element_path(self, item):
        """ Побудова повного шляху до елемента дерева.

        """

        path = []
        while item:
            path.insert(0, item.text())
            item = item.parent()

        return "/" + "/".join(path)

    def get_current_child_count(self, parent_item, child_name):
        """
        Підраховує кількість дочірніх елементів із зазначеним іменем.
        """

        count = 0
        for i in range(parent_item.rowCount()):
            if parent_item.child(i).text() == child_name:
                count += 1
        return count

    def create_add_child_callback(self, parent_item, child_name):
        """
        Створює замикання для додавання дочірнього елемента.
        """

        return lambda: self.add_child(parent_item, child_name)

    def add_child(self, item, child_name):
        """
        Додає дочірній елемент до вказаного елемента дерева.
        """

        child_item = QStandardItem(child_name)
        child_item.setEditable(False)  # Забороняємо редагування назви елемента
        item.appendRow([child_item, QStandardItem("")])

    def change_value(self):
        """
        Змінює значення вибраного елемента.
        """

        index = self.currentIndex()
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        if item:

            new_value = "Новe Значення"  # Український текст
            item.setText(new_value)
            item.setToolTip("Оновлене значення елемента")  # Український опис

    def add_child_item(self):
        """
        Додає дочірній елемент до вибраного елемента.
        """

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

            item_full_path = item.data(Qt.ItemDataRole.UserRole)
            if item_full_path:

                tag_match = re.match(
                    r'(.*/)?([^/\[]+)(\[\d+\])?$', item_full_path)
                item_tag_name = tag_match.group(
                    2) if tag_match else item_full_path.split('/')[-1]

                if item_tag_name in self.elements_to_expand:
                    self.expand(index)

            for row in range(item.rowCount()):
                child_index = model.index(row, 0, index)
                expand_recursively(child_index)

        root_index = model.index(0, 0)
        expand_recursively(root_index)

        return

    def get_item_path(self, item):
        """
        Отримує шлях до елемента в TreeView.
        """
        if not item:
            return ""

        index = item.index()
        if index.column() == 1:

            name_item_index = index.sibling(index.row(), 0)
            path = self.model.data(name_item_index, Qt.ItemDataRole.UserRole)
        else:

            path = self.model.data(index, Qt.ItemDataRole.UserRole)
        return path if path else ""

    def validate_full_name(self, full_name):
        """
        Перевіряє ПІБ на відповідність формату.
        """

        pattern = r"^[А-ЯІЇЄҐ][а-яіїєґ']+ [А-ЯІЇЄҐ][а-яіїєґ'\.]+(?: [А-ЯІЇЄҐ][а-яіїєґ'\.]+)?$"
        return bool(re.match(pattern, full_name))

    def tree_FileDate_update(self, path, value):
        """ Оновлює FileDate у дереві при зміні FileDate у таблиці """
        index_FileDate = self.find_element_index(path)
        if not index_FileDate.isValid():
            return
        item_FileDate = self.model.itemFromIndex(index_FileDate)
        item_FileDate.parent().child(item_FileDate.row(), 1).setText(value)

    def tree_FileGUID_update(self, path, value):
        """ Оновлює FileGUID у дереві при зміні FileGUID у таблиці """
        index_FileGUID = self.find_element_index(path)
        if not index_FileGUID.isValid():
            return
        item_FileGUID = self.model.itemFromIndex(index_FileGUID)
        item_FileGUID.parent().child(item_FileGUID.row(), 1).setText(value)

    def tree_FormatVersion_update(self, path, value):
        """ Оновлює FormatVersion у дереві при зміні FormatVersion у таблиці """
        index_FormatVersion = self.find_element_index(path)
        if not index_FormatVersion.isValid():
            return
        item_FormatVersion = self.model.itemFromIndex(index_FormatVersion)
        item_FormatVersion.parent().child(item_FormatVersion.row(), 1).setText(value)

    def tree_ReceiverName_update(self, path, value):
        """ Оновлює ReceiverName у дереві при зміні ReceiverName у таблиці """
        index_ReceiverName = self.find_element_index(path)
        if not index_ReceiverName.isValid():
            return
        item_ReceiverName = self.model.itemFromIndex(index_ReceiverName)
        item_ReceiverName.parent().child(item_ReceiverName.row(), 1).setText(value)

    def tree_ReceiverIdentifier_update(self, path, value):
        """ Оновлює ReceiverIdentifier у дереві при зміні ReceiverIdentifier у таблиці """
        index_ReceiverIdentifier = self.find_element_index(path)
        if not index_ReceiverIdentifier.isValid():
            return
        item_ReceiverIdentifier = self.model.itemFromIndex(
            index_ReceiverIdentifier)
        item_ReceiverIdentifier.parent().child(
            item_ReceiverIdentifier.row(), 1).setText(value)

    def tree_Software_update(self, path, value):
        """ Оновлює Software у дереві при зміні Software у таблиці """
        index_Software = self.find_element_index(path)
        if not index_Software.isValid():
            return
        item_Software = self.model.itemFromIndex(index_Software)
        item_Software.parent().child(item_Software.row(), 1).setText(value)

    def tree_SoftwareVersion_update(self, path, value):
        """ Оновлює SoftwareVersion у дереві при зміні SoftwareVersion у таблиці """
        index_SoftwareVersion = self.find_element_index(path)
        if not index_SoftwareVersion.isValid():
            return
        item_SoftwareVersion = self.model.itemFromIndex(index_SoftwareVersion)
        item_SoftwareVersion.parent().child(item_SoftwareVersion.row(), 1).setText(value)

    def tree_CRS_update(self, full_path, value):
        """ Оновлює CRS у дереві при зміні CRS у таблиці """
        index_CRS = self.find_element_index(path=full_path, element_name=None)
        if not index_CRS.isValid():
            return

        item_CRS = self.model.itemFromIndex(index_CRS)

        if item_CRS.rowCount() == 0:
            return
        log_msg(
            logFile, f"Елемент CoordinateSystem має {item_CRS.rowCount()} дочірніх елементів.")

        item_CRS_child = item_CRS.child(0)

        if item_CRS_child.text() == "SC63":
            if value.startswith("SC63,"):
                sc63_region = value.split(",")[1].strip()
                item_CRS_child_child = item_CRS_child.child(0)
                log_msg(
                    logFile, f"Старий SC63 район {item_CRS_child_child.text()}")
                item_CRS_child_child.setText(sc63_region)
                log_msg(
                    logFile, f"Оновлений SC63 район {item_CRS_child_child.text()}")
            elif value.startswith("Local"):
                item_CRS_child.setText("Local")
                item_CRS_child_child = item_CRS_child.child(0)
                local_CS_number = value[value.find("(") + 1:value.find(")")]
                log_msg(
                    logFile, f"Новий номер локальної CS: {local_CS_number}")
                item_CRS_child_child.setText(local_CS_number)
            else:
                item_CRS_child.removeRows(0, item_CRS_child.rowCount())
                item_CRS_child.setText(value)

        elif item_CRS_child.text() == "Local":
            if value.startswith("SC63,"):
                item_CRS_child.setText("SC63")
                item_CRS_child_child = item_CRS_child.child(0)
                sc63_region = value.split(",")[1].strip()
                item_CRS_child_child.setText(sc63_region)
            elif value.startswith("Local"):
                local_CS_number = value[value.find("(") + 1:value.find(")")]
                log_msg(
                    logFile, f"Новий номер локальної CS: {local_CS_number}")
                item_CRS_child.child(0).setText(local_CS_number)
            else:
                item_CRS_child.removeRows(0, item_CRS_child.rowCount())
                item_CRS_child.setText(value)

        else:
            if value.startswith("SC63,"):
                sc63_region = value.split(",")[1].strip()
                item_CRS_child.setText("SC63")
                item_CRS_child.appendRow(
                    [QStandardItem(sc63_region), QStandardItem()])
            elif value.startswith("Local"):
                local_CS_number = value[value.find("(") + 1:value.find(")")]
                item_CRS_child.setText("Local")
                item_CRS_child.appendRow(
                    [QStandardItem(local_CS_number), QStandardItem()])
            else:
                item_CRS_child.setText(value)

        return

    def tree_HeightSystem_update(self, path, value):
        """ Оновлює HeightSystem у дереві при зміні HeightSystem у таблиці """
        index_HeightSystem = self.find_element_index(path)
        if not index_HeightSystem.isValid():
            return
        item_HeightSystem = self.model.itemFromIndex(index_HeightSystem)
        item_HeightSystem_child = item_HeightSystem.child(0)
        item_HeightSystem_child.setText(value)

    def tree_MeasurementUnit_update(self, path, value):
        """ Оновлює MeasurementUnit у дереві при зміні MeasurementUnit у таблиці """
        index_MeasurementUnit = self.find_element_index(path)
        if not index_MeasurementUnit.isValid():
            return
        item_MeasurementUnit = self.model.itemFromIndex(index_MeasurementUnit)
        item_MeasurementUnit_child = item_MeasurementUnit.child(0)
        item_MeasurementUnit_child.setText(value)

    def tree_CadastralZoneNumber_update(self, path, value):
        """ Оновлює CadastralZoneNumber у дереві при зміні CadastralZoneNumber у таблиці """
        index_CadastralZoneNumber = self.find_element_index(path)
        if not index_CadastralZoneNumber.isValid():
            return
        item_CadastralZoneNumber = self.model.itemFromIndex(
            index_CadastralZoneNumber)
        item_CadastralZoneNumber.parent().child(
            item_CadastralZoneNumber.row(), 1).setText(value)

    def tree_CadastralQuarterNumber_update(self, path, value):
        """ Оновлює CadastralQuarterNumber у дереві при зміні CadastralQuarterNumber у таблиці """
        index_CadastralQuarterNumber = self.find_element_index(path)
        if not index_CadastralQuarterNumber.isValid():
            return
        item_CadastralQuarterNumber = self.model.itemFromIndex(
            index_CadastralQuarterNumber)
        item_CadastralQuarterNumber.parent().child(
            item_CadastralQuarterNumber.row(), 1).setText(value)

    def tree_ParcelID_update(self, path, value):
        """ Оновлює ParcelID у дереві при зміні ParcelID у таблиці """
        index_ParcelID = self.find_element_index(path)
        if not index_ParcelID.isValid():
            return
        item_ParcelID = self.model.itemFromIndex(index_ParcelID)
        item_ParcelID.parent().child(item_ParcelID.row(), 1).setText(value)

    def tree_LocalAuthorityHead_update(self, path, value):
        """ Оновлює LocalAuthorityHead у дереві при зміні LocalAuthorityHead у таблиці """
        index_LocalAuthorityHead = self.find_element_index(path)
        if not index_LocalAuthorityHead.isValid():
            return

        if not self.validate_full_name(value):
            return

        if len(value.split(" ")) == 2:
            surname, name = value.split(" ")
            MiddleName = ""
        else:
            surname, name, MiddleName = value.split(" ")

        log_msg(
            logFile, f"Прізвище: {surname}, Ім'я: {name}, По батькові: {MiddleName}")

        item_LocalAuthorityHead = self.model.itemFromIndex(
            index_LocalAuthorityHead)

        item_LocalAuthorityHead_child_0 = item_LocalAuthorityHead.child(0)
        pathLastName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/LastName"

        self.find_element_index(pathLastName)

        item_LocalAuthorityHead_child_0.parent().child(item_LocalAuthorityHead_child_0.row(),
                                                       1).setText(surname)

        item_LocalAuthorityHead_child_1 = item_LocalAuthorityHead.child(1)
        pathFirstName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/FirstName"

        self.find_element_index(pathFirstName)

        item_LocalAuthorityHead_child_1.parent().child(
            item_LocalAuthorityHead_child_1.row(), 1).setText(name)

        item_LocalAuthorityHead_child_2 = item_LocalAuthorityHead.child(2)
        pathMiddleName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/MiddleName"

        self.find_element_index(pathMiddleName)

        item_LocalAuthorityHead_child_2.parent().child(
            item_LocalAuthorityHead_child_2.row(), 1).setText(MiddleName)

    def tree_DKZRHead_update(self, path, value):
        """ Оновлює DKZRHead у дереві при зміні DKZRHead у таблиці """
        index_DKZRHead = self.find_element_index(path)
        if not index_DKZRHead.isValid():
            return

        if not self.validate_full_name(value):
            return

        if len(value.split(" ")) == 2:
            surname, name = value.split(" ")
            MiddleName = ""
        else:
            surname, name, MiddleName = value.split(" ")

        log_msg(
            logFile, f"Прізвище: {surname}, Ім'я: {name}, По батькові: {MiddleName}")

        item_DKZRHead = self.model.itemFromIndex(index_DKZRHead)

        item_DKZRHead_child_0 = item_DKZRHead.child(0)
        pathLastName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/LastName"

        self.find_element_index(pathLastName)

        item_DKZRHead_child_0.parent().child(item_DKZRHead_child_0.row(),
                                             1).setText(surname)

        item_DKZRHead_child_1 = item_DKZRHead.child(1)
        pathFirstName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/FirstName"

        self.find_element_index(pathFirstName)

        item_DKZRHead_child_1.parent().child(item_DKZRHead_child_1.row(), 1).setText(name)

        item_DKZRHead_child_2 = item_DKZRHead.child(2)
        pathMiddleName = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead/MiddleName"

        self.find_element_index(pathMiddleName)

        item_DKZRHead_child_2.parent().child(
            item_DKZRHead_child_2.row(), 1).setText(MiddleName)

    def extract_descriptions(self, element, full_path="", ns=None, is_root=False):
        """
        Рекурсивно витягує описи з XSD для елементів, включаючи вкладені структури.
        """
        name = element.get("name")
        ref = element.get("ref")

        if ref:

            ref_element = element.getroottree().xpath(
                f"//xsd:element[@name='{ref}']", namespaces=ns)
            if ref_element:
                self.extract_descriptions(
                    ref_element[0], full_path, ns, is_root=False)
            else:
                print(f"Reference '{ref}' not found in XSD.")
            return

        if name:

            full_path = f"{full_path}/{name}".strip("/") if full_path else name

            documentation = element.xpath(
                './xsd:annotation/xsd:documentation', namespaces=ns)
            if documentation:
                self.xsd_descriptions[full_path] = documentation[0].text.strip(
                )

            appinfo = element.xpath(
                './xsd:annotation/xsd:appinfo', namespaces=ns)
            if appinfo:
                self.xsd_appinfo[full_path] = appinfo[0].text.strip()

        complex_type = element.xpath('./xsd:complexType', namespaces=ns)
        if complex_type:
            for child in complex_type[0].xpath('./xsd:sequence/xsd:element | ./xsd:choice/xsd:element | ./xsd:all/xsd:element', namespaces=ns):
                self.extract_descriptions(child, full_path, ns)

        ref_type = element.get("type")
        if ref_type:
            if ref_type.startswith("xsd:"):

                pass
            else:

                ref_element = element.getroottree().xpath(
                    f"//xsd:complexType[@name='{ref_type}'] | //xsd:simpleType[@name='{ref_type}']", namespaces=ns)
                if ref_element:
                    print(
                        f"Processing type reference '{ref_type}' for element '{name}'")
                    for ref_child in ref_element[0].xpath('./xsd:sequence/xsd:element | ./xsd:choice/xsd:element | ./xsd:all/xsd:element', namespaces=ns):
                        self.extract_descriptions(ref_child, full_path, ns)

    def load_xsd_descriptions(self, path_to_xsd: str):
        """
        Парсує XSD-файл і витягує описи для елементів.
        """

        self.xsd_appinfo = {}
        self.xsd_descriptions = {}
        self.xsd_schema = {}
        try:

            xsd_tree = etree.parse(
                path_to_xsd)
            root = xsd_tree.getroot()

            ns = {'xsd': 'http://www.w3.org/2001/XMLSchema'}

            root_element = root.xpath(
                "//xsd:element[@name='UkrainianCadastralExchangeFile']", namespaces=ns)
            if root_element:
                self._parse_xsd_element(root_element[0], "", ns)
            else:
                log_msg(
                    logFile, "Кореневий елемент 'UkrainianCadastralExchangeFile' не знайдено.")
        except Exception as e:
            log_msg(
                logFile, f"Помилка при парсингу XSD: {e}")

        return self.xsd_descriptions

    def _parse_xsd_element(self, element, parent_path, ns):
        """Рекурсивно парсить XSD, збираючи структуру, типи та обмеження."""
        tag_name = element.get('name')
        if not tag_name:
            ref = element.get('ref')
            if ref:

                ref_element = element.getroottree().xpath(
                    f"//xsd:element[@name='{ref}']", namespaces=ns)
                if ref_element:

                    ref_element[0].set(
                        'minOccurs', element.get('minOccurs', '1'))
                    ref_element[0].set(
                        'maxOccurs', element.get('maxOccurs', '1'))
                    return self._parse_xsd_element(ref_element[0], parent_path, ns)
            return None

        full_path = f"{parent_path}/{tag_name}" if parent_path else tag_name

        element_info = {
            'name': tag_name,
            'minOccurs': element.get('minOccurs', '1'),
            'maxOccurs': element.get('maxOccurs', '1'),
            'children': []

        }

        annotation = element.find('xsd:annotation', ns)
        if annotation is not None:
            doc = annotation.find('xsd:documentation', ns)
            if doc is not None and doc.text:
                self.xsd_descriptions[full_path] = doc.text.strip()
            appinfo = annotation.find('xsd:appinfo', ns)
            if appinfo is not None and appinfo.text:
                self.xsd_appinfo[full_path] = appinfo.text.strip()

        complex_type = element.find('xsd:complexType', ns)
        type_name = element.get('type')

        if complex_type is None and type_name and not type_name.startswith('xsd:'):

            complex_type = element.getroottree().xpath(
                f"//xsd:complexType[@name='{type_name}']", namespaces=ns)
            complex_type = complex_type[0] if complex_type else None

        if complex_type is not None:

            def _append_group_children(group_node, in_choice=False):
                """
                Додає дочірні елементи з урахуванням вкладених sequence/choice/all.
                """
                for node in group_node:
                    local_name = etree.QName(node).localname
                    if local_name == 'element':
                        child_info = self._parse_xsd_element(node, full_path, ns)
                        if child_info:
                            if in_choice:
                                child_info['minOccurs'] = '0'
                            element_info['children'].append(child_info)
                    elif local_name in ('sequence', 'choice', 'all'):
                        _append_group_children(
                            node,
                            in_choice=(in_choice or local_name == 'choice')
                        )

            for group_tag in ['sequence', 'choice', 'all']:
                groups = complex_type.findall(f'xsd:{group_tag}', ns)
                for group in groups:
                    if 'type' not in element_info:
                        element_info['type'] = group_tag
                    _append_group_children(group, in_choice=(group_tag == 'choice'))

        self.xsd_schema[full_path] = element_info
        return element_info

    def _add_element_to_tree(self, element, parent_item, full_path=""):
        """ Рекурсивно додає XML-елементи до моделі дерева, встановлюючи підказки.
        """
        name = etree.QName(element).localname

        if full_path:
            full_path = f"{full_path}/{name}"
        else:
            full_path = name

        display_name = self.xsd_appinfo.get(full_path, name)

        name_item = QStandardItem(display_name)
        value_item = QStandardItem(
            element.text.strip() if element.text else "")

        name_item.setData(full_path, Qt.ItemDataRole.UserRole)
        value_item.setData(full_path, Qt.ItemDataRole.UserRole)

        self.tree_row += 1
        name_item.setData(self.tree_row, Qt.ItemDataRole.UserRole + 1)
        value_item.setData(self.tree_row, Qt.ItemDataRole.UserRole + 1)
        name_item.setData(0, Qt.ItemDataRole.UserRole + 2)
        value_item.setData(1, Qt.ItemDataRole.UserRole + 2)

        description = self.xsd_descriptions.get(full_path, "")
        if description:
            name_item.setToolTip(description)
            value_item.setToolTip(description)

        name_item.setEditable(False)
        value_item.setEditable(False)

        parent_item.appendRow([name_item, value_item])

        if full_path in self.xsd_schema:
            schema = self.xsd_schema[full_path]
            existing_children_tags = {child.tag for child in element}

            for child_schema in schema.get('children', []):
                child_tag = child_schema['name']
                if child_tag not in existing_children_tags and child_schema.get('minOccurs', '1') != '0':

                    new_child = etree.SubElement(element, child_tag)
                    if child_tag in ("Urban", "Rural"):
                        new_child.text = None
                    else:
                        new_child.text = " "

    def load_xml_to_tree_view(self,
                              xml_path: str = "",
                              path_to_xsd: str = "",
                              tree: etree._ElementTree = None):
        """
        Loads an XML file into a tree view and validates it against an XSD schema.
        """

        # log_calls(logFile, f"xml_path={xml_path}\ntree={tree}")

        self.tree_row = 0
        try:

            if not self.xsd_descriptions and path_to_xsd:
                self.xsd_descriptions = self.load_xsd_descriptions(path_to_xsd)

            if tree is not None:
                self.xml_tree = tree
            elif xml_path:
                self.xml_tree = etree.parse(xml_path)

            self.model.removeRows(0, self.model.rowCount())

            root = self.xml_tree.getroot()
        
            def build_tree(xml_node, parent_qt_item, parent_full_path="", parent_schema_path=""):

                preceding_siblings = xml_node.xpath(
                    f'preceding-sibling::{xml_node.tag}')
                index = len(preceding_siblings) + 1

                current_full_path = (
                    f"{parent_full_path}/{xml_node.tag}[{index}]"
                    if parent_full_path else f"{xml_node.tag}[{index}]"
                )
                current_schema_path = (
                    f"{parent_schema_path}/{xml_node.tag}"
                    if parent_schema_path else xml_node.tag
                )

                name_item, value_item = self._create_qt_items_for_element(
                    xml_node, current_full_path, current_schema_path)

                parent_qt_item.appendRow([name_item, value_item])

                for child_xml_node in xml_node:
                    build_tree(
                        child_xml_node,
                        name_item,
                        current_full_path,
                        current_schema_path
                    )

            build_tree(root, self.model.invisibleRootItem())

        except Exception as e:
            log_msg(logFile, f"Помилка при завантаженні XML: {e}")

    def _create_qt_items_for_element(self, element, full_path, schema_path):
        """Створює QStandardItem для елемента та його значення."""
        display_name = self.xsd_appinfo.get(schema_path, element.tag)
        description = self.xsd_descriptions.get(schema_path, "")

        name_item = QStandardItem(display_name)
        name_item.setEditable(False)
        name_item.setData(full_path, Qt.ItemDataRole.UserRole)
        name_item.setData(element, Qt.ItemDataRole.UserRole + 10)
        if description:
            name_item.setToolTip(description)

        is_state_act_type = schema_path.endswith("/StateActInfo/StateActType")
        is_reason_act_doc = schema_path.endswith("/StateActInfo/EntitlementDocument/Document")
        is_category = schema_path.endswith("/CategoryPurposeInfo/Category")
        is_purpose = schema_path.endswith("/CategoryPurposeInfo/Purpose")
        is_ownership_code = schema_path.endswith("/OwnershipInfo/Code")
        is_restriction_code = schema_path.endswith("/RestrictionInfo/RestrictionCode")
        self.doc_code_delegate._is_target_element(
            name_item.index())
        is_doc_type = self.doc_type_delegate._is_target_element(
            name_item.index())
        is_land_code = self.land_code_delegate._is_target_element(
            name_item.index())
        is_closed = self.closed_delegate._is_target_element(name_item.index())
        raw_value_text = element.text.strip() if element.text and element.text.strip() else ""
        value_text = raw_value_text

        if schema_path.endswith("DocumentList"):

            value_text = self.doc_code_delegate.doc_list.get(value_text, value_text)
        elif is_closed:
            value_text = self.closed_delegate.closed_options.get(
                value_text, value_text)

        value_item = QStandardItem(value_text)
        if schema_path.endswith("DocumentList"):
            try:
                value_item.setData(raw_value_text, Qt.ItemDataRole.EditRole)
            except Exception:
                pass

        is_leaf = len(element) == 0
        is_empty_marker = element.tag in ("Urban", "Rural")
        if is_state_act_type or is_category or is_purpose or is_ownership_code or is_doc_type or is_land_code or is_closed or schema_path.endswith("DocumentList"):
            value_item.setEditable(True)
        elif is_empty_marker:
            value_item.setEditable(False)
        else:
            value_item.setEditable(is_leaf)

        value_item.setData(full_path, Qt.ItemDataRole.UserRole)
        value_item.setData(element, Qt.ItemDataRole.UserRole + 10)
        if description:
            value_item.setToolTip(description)
        if is_state_act_type:
            try:
                friendly = None
                try:
                    if "StateActType" in config:
                        friendly = dict(config["StateActType"]).get(str(element.text).strip() if element.text else "")
                except Exception:
                    friendly = None
                if not friendly:
                    friendly = self.state_act_delegate.state_act_types.get(
                        str(element.text).strip() if element.text else "", ""
                    )
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass
        if is_reason_act_doc:
            try:
                friendly = None
                try:
                    if "ReasonActDoc" in config:
                        friendly = dict(config["ReasonActDoc"]).get(str(element.text).strip() if element.text else "")
                except Exception:
                    friendly = None
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass
        if is_restriction_code:
            try:
                friendly = self._restriction_code_name(str(element.text).strip() if element.text else "")
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass
        if is_category:
            try:
                friendly = self.category_delegate.category_types.get(
                    str(element.text).strip() if element.text else "", "")
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass
        if is_purpose:
            try:
                friendly = self.purpose_delegate.all_purposes.get(
                    str(element.text).strip() if element.text else "", "")
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass
        if is_ownership_code:
            try:
                friendly = self.ownership_delegate.ownership_forms.get(
                    str(element.text).strip() if element.text else "", "")
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass
        if is_doc_type:
            try:
                friendly = self.doc_type_delegate.doc_types.get(
                    str(element.text).strip() if element.text else "", "")
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass
        if is_land_code:
            try:
                friendly = self.land_code_delegate.land_codes.get(
                    str(element.text).strip() if element.text else "", "")
                if friendly:
                    tip = value_item.toolTip() or ""
                    if tip:
                        value_item.setToolTip(f"{tip}\n{friendly}")
                    else:
                        value_item.setToolTip(friendly)
            except Exception:
                pass

        return name_item, value_item

    def save_xml_tree(self, xml_tree, xml_path):
        """
        Saves an lxml ElementTree object to a file.
        """

        try:

            root_original = xml_tree.getroot()
            if root_original is None:
                raise Exception("XML tree has no root element.")

            root_to_write = etree.fromstring(etree.tostring(root_original, encoding="utf-8"))
            xml_tree_to_write = etree.ElementTree(root_to_write)

            for node in root_to_write.xpath(".//*[@object_id]"):
                try:
                    del node.attrib["object_id"]
                except Exception:
                    pass



            root = xml_tree_to_write.getroot()
            if root is not None:
                coord_roots = root.xpath(".//*[local-name()='CoordinateSystem']")
                height_roots = root.xpath(".//*[local-name()='HeightSystem']")
                unit_roots = root.xpath(".//*[local-name()='MeasurementUnit']")
                fixed_empty_names = {"USC2000", "WGS84", "X", "C", "P", "T", "Baltic", "Baltic77", "M", "Km", "Urban", "Rural"}
                container_names = {"CoordinateSystem", "SC63", "Local", "HeightSystem", "MeasurementUnit"}
                for branch_root in coord_roots + height_roots + unit_roots:
                    for node in branch_root.iter():
                        try:
                            local_name = etree.QName(node).localname
                        except Exception:
                            local_name = ""

                        is_fixed_empty = local_name in fixed_empty_names
                        is_container = local_name in container_names

                        if (is_fixed_empty or is_container) and node.text is not None and node.text.strip() == "":
                            node.text = None

                for empty_node in root.xpath(".//*[local-name()='Urban' or local-name()='Rural']"):
                    empty_node.text = None

            xml_tree_to_write.write(xml_path, encoding="utf-8", xml_declaration=True)
            print(f"XML file successfully saved to: {xml_path}")
        except OSError as e:
            raise Exception(f"Error saving XML file to {xml_path}: {e}") from e

    def find_element_index(self, path=None, element_name=None):
        """
            Знаходить індекс елемента у дереві на основі шляху або імені.
        """

        if path:

            current_index = QModelIndex()
            path_parts = path.split("/")  # Розділяємо шлях на частини
            for part in path_parts:
                found = False
                for row in range(self.model.rowCount(current_index)):
                    child_index = self.model.index(row, 0, current_index)
                    child_item = self.model.itemFromIndex(child_index)
                    if child_item and child_item.text() == part:

                        current_index = child_index
                        found = True
                        break
                if not found:

                    return QModelIndex()
            return current_index
        elif element_name:

            for row in range(self.model.rowCount()):

                item = self.model.item(row, 0)
                if item and item.text() == element_name:
                    return self.model.indexFromItem(item)

        return QModelIndex()

    def _generate_ukr_path(self, path_str):
        """Створює читабельний український шлях (хлібні крихти)."""
        if not path_str:
            return ""
        parts = path_str.split('/')
        ukr_parts = []
        for i in range(len(parts)):
            current_sub_path = "/".join(parts[:i+1])

            ukr_name = self.xsd_appinfo.get(current_sub_path, parts[i])
            ukr_parts.append(ukr_name)
        return " -> ".join(ukr_parts)

    def _validate_and_color_tree(self, generate_report=False):
        """
        Рекурсивно обходить дерево, валідує елементи та зафарбовує їх у разі помилки.
        """
        default_brush = QBrush(Qt.GlobalColor.black)
        error_brush = QBrush(QColor("red"))
        errors = []

        self.validation_errors.clear()  # Очищуємо словник помилок
        self.tree_upd = True

        def clear_colors(item):
            """Рекурсивний скидає колір для елемента та його дочірніх елементів."""
            item.setForeground(default_brush)
            value_item = item.parent().child(
                item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
            if value_item:
                value_item.setForeground(default_brush)
            for row in range(item.rowCount()):
                clear_colors(item.child(row, 0))

        if self.model.invisibleRootItem().hasChildren():
            clear_colors(self.model.invisibleRootItem().child(0, 0))

        def clear_tooltips(item):
            """Рекурсивно очищує старі помилки з підказок."""
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self.xsd_descriptions:
                base_tooltip = self.xsd_descriptions[path]
                item.setToolTip(base_tooltip)
                value_item = item.parent().child(
                    item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
                if value_item:
                    value_item.setToolTip(base_tooltip)

            for row in range(item.rowCount()):
                child_item = item.child(row, 0)
                if child_item:
                    clear_tooltips(child_item)

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

                ukr_name = self.xsd_appinfo.get(current_sub_path, parts[i])
                ukr_parts.append(ukr_name)
            return " -> ".join(ukr_parts)

        def traverse_and_validate(item):
            """
            Рекурсивна функція. Повертає True, якщо гілка валідна, інакше False.
            """
            path = item.data(Qt.ItemDataRole.UserRole)
            xml_element = self._find_xml_element_by_path(path)
            direct_item_errors = []  # Помилки безпосередньо цього елемента
            child_errors = []  # Помилки, зібрані з дочірніх елементів

            has_invalid_child = False
            for row in range(item.rowCount()):
                child_item = item.child(row, 0)
                is_child_branch_valid, collected_child_errors = traverse_and_validate(
                    child_item)
                if not is_child_branch_valid:
                    has_invalid_child = True
                    child_errors.extend(
                        collected_child_errors)  # Збираємо помилки з дочірніх гілок

            is_self_valid = validate_element(xml_element, path)
            if not is_self_valid and generate_report:
                self._generate_ukr_path(path)

                ukr_name = item.text().rstrip(" ⋮↵")
                value = xml_element.text if xml_element is not None else "N/A"

                error_msg = f"В елементі '{ukr_name}' некоректне значення: '{value}'"
                direct_item_errors.append(error_msg)

                errors.append(error_msg)

            is_structure_valid = True

            self._generate_ukr_path(path)
            if path in self.xsd_schema and xml_element is not None:
                schema = self.xsd_schema[path]
                if 'children' in schema:
                    existing_children_tags = {
                        child.tag for child in xml_element}

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

                                errors.append(error_msg)
                    else:  # Перевірка для xsd:sequence та xsd:all
                        for child_schema in schema.get('children', []):
                            if schema.get('type') != 'choice' and child_schema.get('minOccurs', '1') != '0' and child_schema['name'] not in existing_children_tags:
                                is_structure_valid = False
                                if generate_report:

                                    child_ukr_name = self.xsd_appinfo.get(
                                        f"{path}/{child_schema['name']}", child_schema['name']).rstrip(" ⋮↵")
                                    parent_ukr_name = item.text().rstrip(" ⋮↵")

                                    error_msg = f"В елементі '{parent_ukr_name}' відсутній піделемент '{child_ukr_name}'"
                                    direct_item_errors.append(error_msg)

                                    errors.append(error_msg)

            is_branch_valid = is_self_valid and is_structure_valid and not has_invalid_child

            has_direct_error = not is_self_valid or not is_structure_valid

            brush_to_set = error_brush if has_direct_error else default_brush
            item.model().setData(item.index(), brush_to_set, Qt.ItemDataRole.ForegroundRole)
            value_item = item.parent().child(
                item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
            if value_item:
                value_item.model().setData(value_item.index(), brush_to_set, Qt.ItemDataRole.ForegroundRole)

            if has_direct_error:
                parent = item.parent()
                while parent and parent.index().isValid():
                    self.expand(parent.index())
                    parent = parent.parent()

            base_tooltip = self.xsd_descriptions.get(path, "")
            value_item = item.parent().child(
                item.row(), 1) if item.parent() else self.model.item(item.row(), 1)

            tooltip_errors = []
            tooltip_header = "ПОМИЛКИ:"

            if direct_item_errors:

                tooltip_errors = direct_item_errors

            if direct_item_errors:
                self.validation_errors[path] = direct_item_errors

            if tooltip_errors:
                error_tooltip_part = f"\n\n{tooltip_header}\n- " + \
                    "\n- ".join(tooltip_errors)
                item.setToolTip(base_tooltip + error_tooltip_part)
                if value_item:
                    value_item.setToolTip(base_tooltip + error_tooltip_part)

            return is_branch_valid, direct_item_errors

        try:
            root_item = self.model.invisibleRootItem().child(0, 0)
            if root_item:
                traverse_and_validate(root_item)
            return errors
        finally:
            self.tree_upd = False

    def _normalize_xpath_path(self, path_str):
        """
        Нормалізує XPath до формату шляхів у Qt.ItemDataRole.UserRole: Tag[1]/Child[2]/...
        """
        if not path_str:
            return ""

        path = str(path_str).strip()
        if path.startswith("/"):
            path = path[1:]

        path = re.sub(r"(^|/)([A-Za-z_][\w\.-]*):", r"\1", path)
        path = re.sub(r"\{[^}]+\}", "", path)

        parts = []
        for part in path.split("/"):
            part = part.strip()
            if not part:
                continue
            if "[" not in part:
                part = f"{part}[1]"
            parts.append(part)
        return "/".join(parts)

    def _iter_name_items(self):
        """Ітерує всі елементи колонки 0."""
        root_item = self.model.invisibleRootItem().child(0, 0)
        if not root_item:
            return

        stack = [root_item]
        while stack:
            item = stack.pop()
            yield item
            for row in range(item.rowCount() - 1, -1, -1):
                child_item = item.child(row, 0)
                if child_item:
                    stack.append(child_item)

    def _find_item_by_xpath_path(self, xpath_path):
        """Знаходить елемент дерева, що відповідає XPath з XSD-помилки."""
        normalized_target = self._normalize_xpath_path(xpath_path)
        if not normalized_target:
            return self.model.invisibleRootItem().child(0, 0)

        normalized_to_item = {}
        items_iter = self._iter_name_items()
        if items_iter:
            for item in items_iter:
                item_path = item.data(Qt.ItemDataRole.UserRole) or ""
                norm_item_path = self._normalize_xpath_path(item_path)
                if norm_item_path:
                    normalized_to_item[norm_item_path] = item

        if normalized_target in normalized_to_item:
            return normalized_to_item[normalized_target]

        parent_path = normalized_target
        while "/" in parent_path:
            parent_path = parent_path.rsplit("/", 1)[0]
            if parent_path in normalized_to_item:
                return normalized_to_item[parent_path]

        return self.model.invisibleRootItem().child(0, 0)

    def validate_against_xsd(self, path_to_xsd, generate_report=False, reset_visuals=True, xml_tree=None):
        """
        Перевіряє XML-дерево на відповідність XSD та підсвічує помилки.
        НЕ змінює XML-структуру/значення.
        """
        errors = []
        active_tree = xml_tree if xml_tree is not None else self.xml_tree
        if active_tree is None:
            return ["XML дерево не завантажено."]
        if not path_to_xsd or not os.path.exists(path_to_xsd):
            return [f"XSD схему не знайдено: {path_to_xsd}"]

        self.tree_upd = True
        try:
            if reset_visuals:

                root_item = self.model.invisibleRootItem().child(0, 0)
                if root_item:
                    default_brush = QBrush(Qt.black)
                    stack = [root_item]
                    while stack:
                        curr = stack.pop()
                        curr.setForeground(default_brush)
                        curr_path = curr.data(Qt.ItemDataRole.UserRole) or ""
                        schema_path = re.sub(r"\[\d+\]", "", curr_path)
                        base_tooltip = self.xsd_descriptions.get(schema_path, "")
                        curr.setToolTip(base_tooltip)
                        value_item = curr.parent().child(
                            curr.row(), 1) if curr.parent() else self.model.item(curr.row(), 1)
                        if value_item:
                            value_item.setForeground(default_brush)
                            value_item.setToolTip(base_tooltip)
                        for row in range(curr.rowCount() - 1, -1, -1):
                            child_item = curr.child(row, 0)
                            if child_item:
                                stack.append(child_item)
                self.validation_errors.clear()

            try:
                schema_doc = etree.parse(path_to_xsd)
                schema = etree.XMLSchema(schema_doc)
                is_valid = schema.validate(active_tree)
            except Exception as e:
                return [f"Помилка завантаження/перевірки XSD: {e}"]

            if is_valid:
                return []

            for err in schema.error_log:
                err_path = getattr(err, "path", "") or ""
                raw_message = str(getattr(err, "message", str(err)))
                item = self._find_item_by_xpath_path(err_path)

                item_path = item.data(Qt.ItemDataRole.UserRole) if item else ""
                schema_path = re.sub(r"\[\d+\]", "", item_path or "")

                err_message = self._translate_xsd_error_message(raw_message, schema_path=schema_path)
                log_calls(logFile, f"err_message={err_message}")
                self._mark_item_as_invalid(item, err_message)

                if generate_report:
                    readable_path = self._generate_ukr_path(
                        re.sub(r"\[\d+\]", "", item_path or ""))
                    if not readable_path:
                        readable_path = err_path or "XML"
                    errors.append(f"{readable_path}: {err_message}")

            return errors
        finally:
            self.tree_upd = False

    def _translate_xsd_error_message(self, message: str, schema_path: str = "") -> str:
        """
        Перекладає типові повідомлення XSD-валідації (lxml) українською.

        Це евристичний переклад: lxml повертає англомовні шаблонні фрази,
        тож ми покращуємо UX, не змінюючи семантику помилки.
        """
        if not message:
            return message

        msg = str(message)

        def _short_appinfo(text: str) -> str:
            if text is None:
                return ""
            s = str(text).strip()
            # У XSD часто використовується "⋮" та "↓" як маркери UI.
            s = s.replace("⋮", "").replace("↓", "").strip()
            # Приберемо зайві подвійні пробіли після заміни.
            s = re.sub(r"\s{2,}", " ", s)
            return s

        def _appinfo_for_tag(tag_name: str) -> str:
            """
            Повертає український appinfo для елемента XSD за його ім'ям.
            Спочатку пробує знайти за контекстним шляхом (schema_path), потім — глобально.
            """
            if not tag_name:
                return ""

            # 1) Точний контекст (якщо schema_path вже вказує на цей елемент)
            if schema_path:
                if schema_path.endswith(f"/{tag_name}") or schema_path == tag_name:
                    label = self.xsd_appinfo.get(schema_path, "")
                    if label:
                        return _short_appinfo(label)

                parent_path = schema_path.rsplit("/", 1)[0] if "/" in schema_path else ""
                if parent_path:
                    label = self.xsd_appinfo.get(f"{parent_path}/{tag_name}", "")
                    if label:
                        return _short_appinfo(label)

            # 2) Глобальний пошук по xsd_appinfo (перший збіг)
            try:
                suffix = f"/{tag_name}"
                for k, v in self.xsd_appinfo.items():
                    if k == tag_name or str(k).endswith(suffix):
                        if v:
                            return _short_appinfo(v)
            except Exception:
                log_calls(logFile, "Помилка: Глобальний пошук по xsd_appinfo (перший збіг)")

            return ""

        replacements = {
            "Element ": "Елемент ",
            "attribute ": "атрибут ",
            "The attribute ": "Атрибут ",
            "is not allowed.": "не дозволено.",
            "This element is not expected.": "Цей елемент не очікується.",
            "Missing child element(s).": "Відсутній дочірній елемент(и).",
            "Expected is": "Очікується",
            "Expected one of": "Очікується один із",
            "The value ": "Значення ",
            "is not accepted by the pattern": "не відповідає шаблону",
            "fails to satisfy the fixed value constraint": "не відповідає фіксованому значенню",
            "is not a valid value": "є некоректним значенням",
        }
        for src, dst in replacements.items():
            msg = msg.replace(src, dst)

        # Підміна назв елементів на український appinfo
        # 1) Element 'TagName'
        def _replace_element_name(match):
            tag_name = match.group(1)
            label = _appinfo_for_tag(tag_name)
            return f"Елемент '{label or tag_name}'"

        try:
            msg = re.sub(r"Елемент '([^']+)'", _replace_element_name, msg)
        except Exception:
            log_calls(logFile, "Помилка: Підміна назв елементів на український appinfo")

        # 2) Expected is ( A ) / Expected one of ( A, B )
        def _replace_expected_list(match):
            inner = match.group(1)
            tokens = [t.strip() for t in re.split(r"[,\s]+", inner) if t.strip()]
            # lxml може писати імена з комами, інколи з кількома пробілами
            mapped = []
            for tok in tokens:
                # пропускаємо службові символи/дужки, якщо раптом потрапили
                clean = tok.strip("()")
                if not clean:
                    continue
                label = _appinfo_for_tag(clean)
                mapped.append(label or clean)
            return "(" + ", ".join(mapped) + ")"

        try:
            msg = re.sub(r"\(\s*([A-Za-z0-9_,\s]+?)\s*\)", _replace_expected_list, msg)
        except Exception:
            log_calls(logFile, "Error: Expected is ( A ) / Expected one of ( A, B )")

        try:
            msg = re.sub(
                r"The attribute '([^']+)' is not allowed\.",
                r"Атрибут '\1' не дозволено.",
                msg,
            )
        except Exception:
            log_calls(logFile, "Помилка: The attribute not allowed")

        return msg


    def _mark_item_as_invalid(self, item, error_message):
        """Підсвічує елемент/значення червоним і додає помилку в tooltip."""
        if not item:
            return
        log_calls(logFile,f"item={item}\nerror_message={error_message}")

        error_brush = QBrush(QColor("red"))
        item.setForeground(error_brush)
        value_item = item.parent().child(
            item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
        if value_item:
            value_item.setForeground(error_brush)

        item_path = item.data(Qt.ItemDataRole.UserRole) or item.text()
        self.validation_errors.setdefault(item_path, [])
        if error_message not in self.validation_errors[item_path]:
            self.validation_errors[item_path].append(error_message)

        schema_path = re.sub(r"\[\d+\]", "", item_path)
        base_tooltip = self.xsd_descriptions.get(schema_path, "")
        tooltip_text = base_tooltip
        if self.validation_errors[item_path]:
            tooltip_text += "\n\nПОМИЛКИ:\n- " + \
                "\n- ".join(self.validation_errors[item_path])
        item.setToolTip(tooltip_text)
        if value_item:
            value_item.setToolTip(tooltip_text)

        parent = item.parent()
        while parent and parent.index().isValid():
            self.expand(parent.index())
            parent = parent.parent()


    def highlight_xml_errors(self, validation_results):
        """
        Підсвічує червоним кольором елементи дерева з помилками валідації XSD,
        розкриває гілки до цих елементів та додає описання помилок у підказки (tooltips).

        Args:
            validation_results (list): Список помилок або результатів валідації XSD.
        """
        if not validation_results:
            return

        error_brush = QBrush(QColor("red"))

        for error in validation_results:
            xpath_path = getattr(error, 'path', None) or getattr(error, 'element_path', '')
            message = getattr(error, 'message', str(error))

            item = self._find_item_by_xpath_path(xpath_path)
            if item:
                # 1. Зафарбовуємо назву елемента та його значення
                item.setForeground(error_brush)
                value_item = item.parent().child(item.row(), 1) if item.parent() else self.model.item(item.row(), 1)
                if value_item:
                    value_item.setForeground(error_brush)

                # 2. Оновлюємо підказку (tooltip)
                current_tooltip = item.toolTip() or ""
                if "ПОМИЛКА XSD:" not in current_tooltip:
                    new_tooltip = f"{current_tooltip}\n\nПОМИЛКА XSD:\n- {message}".strip()
                else:
                    new_tooltip = f"{current_tooltip}\n- {message}".strip()

                item.setToolTip(new_tooltip)
                if value_item:
                    value_item.setToolTip(new_tooltip)

                # 3. Розкриваємо батьківські вузли дерева
                parent = item.parent()
                while parent and parent.index().isValid():
                    self.expand(parent.index())
                    parent = parent.parent()

    def _restriction_code_name(self, code: str) -> str:
        try:
            code = str(code or "").strip()
        except Exception:
            code = ""
        if not code:
            return ""
        try:
            flat = getattr(self, "restrictions_all_codes", None) or {}
            nm = flat.get(code, "")
            if nm:
                return str(nm)
        except Exception:
            pass

        try:
            for section in (self.restrictions_data or {}).values():
                if code in section:
                    return str(section.get(code) or "")
        except Exception:
            pass
        return ""

    def sort_xml_tree_by_xsd(self):
        """
        Впорядковує дочірні елементи XML-дерева згідно з порядком children у xsd_schema.
        Повертає True, якщо були внесені зміни.
        """
        if self.xml_tree is None:
            return False
        root = self.xml_tree.getroot()
        if root is None or not self.xsd_schema:
            return False

        def _lname(node):
            try:
                return etree.QName(node).localname
            except Exception:
                return node.tag

        def _reorder(element, schema_path):
            changed_local = False

            for child in list(element):
                child_schema_path = f"{schema_path}/{_lname(child)}" if schema_path else _lname(child)
                if _reorder(child, child_schema_path):
                    changed_local = True

            schema = self.xsd_schema.get(schema_path, {})
            children_schema = schema.get("children", [])
            expected_order = [child.get("name") for child in children_schema if child.get("name")]
            if not expected_order:
                return changed_local

            children = list(element)
            buckets = {}
            for child in children:
                buckets.setdefault(_lname(child), []).append(child)

            ordered = []
            used_ids = set()
            for tag_name in expected_order:
                for child in buckets.get(tag_name, []):
                    ordered.append(child)
                    used_ids.add(id(child))

            for child in children:
                if id(child) not in used_ids:
                    ordered.append(child)

            if len(ordered) == len(children) and any(ordered[i] is not children[i] for i in range(len(children))):
                for child in children:
                    element.remove(child)
                for child in ordered:
                    element.append(child)
                changed_local = True

            return changed_local

        root_schema_path = _lname(root)
        return _reorder(root, root_schema_path)

