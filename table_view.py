# -*- coding: utf-8 -*-
"""Таблиця метаданих """
import os
import uuid

from datetime import datetime

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtCore import QModelIndex

from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QMenu

from qgis.PyQt.QtWidgets import QTableView
from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QStandardItemModel
from qgis.PyQt.QtCore import pyqtSignal

# from .date_delegate import DateMaskDelegate
from .date_dialog import DateInputDialog

from .common import logFile
from .common import log_msg
from .common import config

def select_receiver_name(parent=None):
    """
    Вибір зі списку назв обласних філій (з ini-файлу).
    """
    log_msg(logFile)
    # config = configparser.ConfigParser()
    # config.read(config, encoding="utf-8")

    if "Receiver" not in config:
        QMessageBox.warning(parent, "Помилка", "Розділ 'Receiver' не знайдено в ini-файлі.")
        return None, None

    receiver_names = list(config["Receiver"].values())
    receiver_keys = list(config["Receiver"].keys())

    selected_name, ok = QInputDialog.getItem(parent, "Вибір філії",
                                             "Оберіть назву обласної філії ЦДЗК:",
                                             receiver_names, 0, False)
    if ok and selected_name:
        index = receiver_names.index(selected_name)
        return receiver_names, receiver_keys[index]
    return None, None
def set_software_value(parent=None):
    """
    Встановлення значення 'QGIS xml_ua'.
    """
    log_msg(logFile)
    reply = QMessageBox.question(parent, "Встановлення значення",
                                 "Встановити значення 'QGIS xml_ua'?",
                                 QMessageBox.Yes | QMessageBox.No)
    if reply == QMessageBox.Yes:
        return "QGIS xml_ua"
    return None
def set_software_version(plugin_directory, parent=None):
    """
        Встановлення значення дати останньої зміни файлів *.py і *.ui.
    """
    log_msg(logFile)
    latest_date = None

    for root, _, files in os.walk(plugin_directory):
        for file in files:
            if file.endswith(".py") or file.endswith(".ui"):
                file_path = os.path.join(root, file)
                modified_time = os.path.getmtime(file_path)
                file_date = datetime.fromtimestamp(modified_time).strftime("%Y.%m.%d")
                if not latest_date or file_date > latest_date:
                    latest_date = file_date

    if latest_date:
        reply = QMessageBox.question(parent, "Встановлення версії",
                                     f"Встановити значення останньої дати зміни: {latest_date}?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            return latest_date
    else:
        QMessageBox.warning(parent, "Помилка", "Не знайдено файлів *.py або *.ui у каталозі плагіну.")
    return None
def handle_metadata_edit(row_name, plugin_directory=None, parent=None):
    """
        Визначає, який діалог викликати для конкретного рядка.
    """
    log_msg(logFile)
    if row_name == "FileDate":
        return input_date(parent)
    elif row_name == "FileGUID":
        return regenerate_guid(parent)
    elif row_name == "ReceiverName":
        return select_receiver_name(parent)
    elif row_name == "ReceiverIdentifier":
        _, identifier = select_receiver_name(parent)
        return identifier
    elif row_name == "Software":
        return set_software_value(parent)
    elif row_name == "SoftwareVersion":
        return set_software_version(plugin_directory, parent)
    else:
        QMessageBox.warning(parent, "Помилка", f"Редагування для {row_name} не підтримується.")
        return None
def set_tooltips_for_table(model, tooltips):

    """
        Встановлює tooltips для рядків моделі таблиці.
        :param model: QStandardItemModel, модель таблиці.
        :param tooltips: dict, словник {ім'я рядка: tooltip}.
    """

    log_msg(logFile)

    if not model:
        # log_var(logFile, "Модель таблиці не встановлена!")
        return

    for row in range(model.rowCount()):  # Перевіряємо всі рядки таблиці

        key_item = model.item(row, 0)  # Отримуємо елемент у першій колонці

        # # log_var(logFile, f"key_item = {key_item}")
        # # log_var(logFile, f"key_item.text() = {key_item.text()}")

        if key_item and key_item.text() in tooltips:

            tooltip_text = tooltips[key_item.text()]
            key_item.setToolTip(tooltip_text)  # Встановлюємо tooltip

class TableViewMetadata(QTableView):
    """
        Клас таблиці для відображення та роботи з метаданими.

        Рядок   Значення:Тип
        0       дата:текст

        populate_tableview_metadata - додаємо елемент по порядку у XSD схемі
        metadata_handle_right_click - якщо є специфічне контекстне меню (за порядковим номером)
        on_item_changed_metadata    - зміна дзеркального елемента у дереві
    """
    metadataChangedSignal = pyqtSignal(str, str)  # Сигнал для оновлення даних
    def __init__(self, parent=None):

        super().__init__(parent)
        # log_msg(logFile, f"parent = {parent}")

        # Явно зберігаємо батьківський об'єкт
        self.parent = parent
        # log_msg(logFile, f"parent = {parent}")

        # (logFile, "Створення моделі таблиці")
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Елемент", "Значення"])
        self.setModel(self.model)

        # log_msg(logFile, "Підключаємо обробку зміни елементів")
        self.model.itemChanged.connect(self.on_item_changed_metadata)

        # Обробка правого кліку
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.metadata_handle_right_click)

        # Змінити висоту горизонтального заголовка
        self.horizontalHeader().setFixedHeight(30)  # Встановити висоту 30 пікселів
        self.verticalHeader().setDefaultSectionSize(30)
        # Встановлення обробника подвійного кліку
        self.doubleClicked.connect(self.handle_double_click)
        self.tooltips = dict(config['metaDataTooltips'])
        # log_dict(logFile, self.tooltips, msg="tooltips")

        # log_msg(logFile, "Створюємо модель даних таблиці")
        self.metadata_model = QStandardItemModel()
        self.metadata_model.setHorizontalHeaderLabels(["Елемент", "Значення"])
        self.setModel(self.metadata_model)
    def handle_double_click(self, index: QModelIndex):
        """
        Обробляє  клік для виклику .
        """
        log_msg(logFile)

        if not index.isValid():
            log_msg(logFile, "Клік поза межами таблиці")
            return

        row = index.row()
        column = index.column()
        value = self.model.data(index)  # Отримуємо значення з моделі

        # QMessageBox.warning(None, "Повідомлення", f"Подвійний клік на рядку {row}, колонці {column}, значення: {value}")
        log_msg(logFile, f"Подвійний клік на рядку {row}, колонці {column}, значення: {value}")
    def metadata_handle_right_click(self, position):
        """ Обробка події правого кліка таблиці метаданих
        """
        index = self.indexAt(position)  # Отримуємо QModelIndex за позицією
        log_msg(logFile, f"index({index.column()}, {index.row()})")
        if not index.isValid():
            log_msg(logFile, "Клік поза межами таблиці")
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
                    self.metadata_model.setData(index, new_guid, Qt.EditRole)
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
                        value_index = self.metadata_model.index(3, 1)
                        self.metadata_model.setData(value_index, selected_value)

                        # Записуємо ключ у комірку (row = 4, col = 1)
                        key_index = self.metadata_model.index(4, 1)
                        self.metadata_model.setData(key_index, selected_key)
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
                    log_msg(logFile, f"selected_system = {selected_system}")
                    # Оновлюємо таблицю
                    # log_msg(logFile, f"self.metadata_model = {self.metadata_model}")
                    self.metadata_model.setData(index, selected_system, Qt.EditRole)
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
                    self.metadata_model.setData(index, selected_system, Qt.EditRole)
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
                    self.metadata_model.setData(index, selected_unit, Qt.EditRole)
            # index.row() == 10: Номер кадастрової зони - нема контекстного меню
            # index.row() == 11: Номер кадастрового кварталу - нема контекстного меню
            # index.row() == 12: TODO Прізвище, ім’я та по батькові керівника органу виконавчої влади або місцевого самоврядування
            # index.row() == 13: TODO Прізвище, ім’я та по батькові начальника територіального органу земельних ресурсів
            # index.row() == 14: Номер земельної ділянки - нема контекстного меню
    def metadata_set_date_dialog(self, index):
        """ Відкриття діалогу вводу дати
        """
        current_value = index.data(Qt.EditRole)
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
            self.metadata_model.setData(index, new_date_str, Qt.EditRole)
        else:
            log_msg(logFile, f"dialog.exec_() != QDialog.Accepted")
    def populate_tableview_metadata(self, xmlTree):
        """ Заповнює таблицю даними, встановлює підказки

            На початку таблиці розміщені дані розділу .//ServiceInfo

            Параметри
                xmlTree: завантажене дерево xml
                self.tooltips: підказки для розділу .//ServiceInfo
        """
        # log_msg(logFile, "Заповнюємо таблицю даними ")
        root_tag = "UkrainianCadastralExchangeFile"

        service_info_path = f"{root_tag}/AdditionalPart/ServiceInfo"
        service_info_element = xmlTree.find("./AdditionalPart/ServiceInfo")

        if service_info_element is None:
            log_msg(self.logFile, f"Розділ ServiceInfo не знайдено.")
            return

        # log_msg(logFile, "Додаємо дані розділу /ServiceInfo")
        # FileDate
        # FileGUID
        for child in service_info_element:
            if child.tag == "FileID":
                # Розбиваємо FileID на FileDate та FileGUID
                file_date = child.find("FileDate")
                # log_msg(logFile, f"file_date = {file_date}")
                file_guid = child.find("FileGUID")

                if file_date is not None:
                    # log_msg(logFile, f"file_date is not None")
                    full_path = f"{service_info_path}/FileID/FileDate"
                    ukr_description = self.parent.get_tooltip_from_tree(full_path, "FileDate")
                    # log_msg(logFile, f"ukr_description = {ukr_description}")

                    key_item = QStandardItem(ukr_description)
                    value_item = QStandardItem(file_date.text.strip() if file_date.text else "")
                    key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях

                    # Вимикаємо редагування для елементів таблиці
                    key_item.setEditable(False)
                    value_item.setEditable(True)

                    key_item.setToolTip(self.tooltips.get("FileDate", ""))

                    self.metadata_model.appendRow([key_item, value_item])
                    # log_msg(logFile, f"appendRow date")

                    # Створення та встановлення делегата
                    # delegate = DateMaskDelegate(self)
                    # log_msg(logFile, f"delegate = {delegate}")
                    # self.setItemDelegateForRow(0, delegate)

                if file_guid is not None:
                    full_path = f"{service_info_path}/FileID/FileGUID"
                    ukr_description = self.parent.get_tooltip_from_tree(full_path, "FileGUID")

                    key_item = QStandardItem(ukr_description)
                    value_item = QStandardItem(file_guid.text.strip() if file_guid.text else "")
                    key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях

                    # Вимикаємо редагування для елементів таблиці
                    key_item.setEditable(False)
                    value_item.setEditable(True)

                    key_item.setToolTip(self.tooltips.get("FileGUID", ""))

                    self.metadata_model.appendRow([key_item, value_item])
            else:
                full_path = f"{service_info_path}/{child.tag}"
                ukr_description = self.parent.get_tooltip_from_tree(full_path, child.tag)

                key_item = QStandardItem(ukr_description)
                value_item = QStandardItem(child.text.strip() if child.text else "")
                key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях

                # Вимикаємо редагування для елементів таблиці
                key_item.setEditable(False)
                value_item.setEditable(True)

                key_item.setToolTip(self.tooltips.get(child.tag, ""))

                self.metadata_model.appendRow([key_item, value_item])

        # CoordinateSystem
        # log_msg(logFile, "Додаємо дані і tooltip CRS")
        for element in xmlTree.findall(".//CoordinateSystem"):
            # Обробляємо систему координат
            value = self.read_coordinate_system(element)

            # Додаємо рядок до таблиці
            key_item = QStandardItem("Система координат")

            full_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/CoordinateSystem"
            key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях

            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Дозволяє лише вибір і активацію
            key_item.setToolTip(
                "<b>Оберіть систему координат</b> (правим кліком на значенні)<br>"
                "Для SC63 район X підходить для більшості території України)<br>"
                "Для місцевої СК (Local) введіть реєстраційний номер у форматі<br>"
                "МСК-XX (де XX - цифровий код місцевості"
            )
            value_item = QStandardItem(value)
            if "Local" in value:
                value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)
            self.metadata_model.appendRow([key_item, value_item])

        # HeightSystem
        # log_msg(logFile, "Додаємо дані і tooltip для HeightSystem")
        for element in xmlTree.findall(".//HeightSystem"):
            # Обробляємо систему висот
            value = self.read_height_system(element)

            #
            key_item = QStandardItem("Система висот")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
            key_item.setToolTip(
                "<b>Оберіть систему висот</b> (правим кліком на значенні)<br>"
                "Можливі значення:<br>"
                "Baltic (Балтійська застаріла)<br>"
                "Baltic77 (чинна Балтійська уточнена)<br>"
                "Other інша<br>"
            )

            full_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/HeightSystem"
            key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях

            value_item = QStandardItem(value)

            self.metadata_model.appendRow([key_item, value_item])

        # MeasurementUnit
        # log_msg(logFile, "Додаємо дані і tooltip MeasurementUnit")
        metric_info = xmlTree.find(".//MetricInfo")
        if metric_info is not None:
            # Пошук MeasurementUnit
            measurement_unit = metric_info.find("MeasurementUnit")
            if measurement_unit is not None:
                # Пошук дочірнього елемента всередині MeasurementUnit
                child_elements = list(measurement_unit)
                if child_elements:
                    value = child_elements[0].tag  # Беремо ім'я першого дочірнього елемента
                else:
                    value = "Unknown"
            else:
                value = "Unknown"

            # log_msg(logFile, f"value (довжина) = {value}")

            # Додавання до таблиці
            key_item = QStandardItem("Одиниця виміру довжини")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
            key_item.setToolTip(
                "<b>Оберіть одиницю виміру</b><br>"
                "Можливі значення:<br>"
                "M (метри)<br>"
                "Km (кілометри)<br>"
                "Other (інша)<br>"
            )

            full_path = "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/MeasurementUnit"
            key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях

            value_item = QStandardItem(value)
            value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)  # Дозволяємо редагування

            self.metadata_model.appendRow([key_item, value_item])
        else:
            log_msg(logFile, "MetricInfo not found in XML.")

        # CadastralZoneNumber
        # log_msg(logFile, "Додаємо дані і tooltip кадастрової зони")
        cadastral_zone_number = xmlTree.find(".//InfoPart/CadastralZoneInfo/CadastralZoneNumber")
        if cadastral_zone_number is not None:
            value = cadastral_zone_number.text.strip() if cadastral_zone_number.text else ""
        else:
            value = ""
        # log_msg(logFile, f"value = {value}")
        key_item = QStandardItem("Номер кадастрової зони")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
        key_item.setToolTip(
            "<b>Номер кадастрової зони</b><br>"
            "Формат: ООРРРСССНН:ЗЗ, де:<br>"
            " ОО - двозначний номер області або міста республіканського підпорядкування<br>"
            "РРР - тризначний номер району або міста обласного підпорядкування (до 2020р)<br>"
            "ССС - тризначний номер сільської ради (до 2020р) або смт<br>"
            " НН - як правило '00', або двозначний номер населеного пункту в межах сільради<br>"
            " ЗЗ - номер кадастрової зони"
        )
        full_path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralZoneNumber"
        key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
        value_item = QStandardItem(value)
        value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)  # Дозволяємо редагування
        # Перевірка на відповідність масці
        if not self.validate_cad_zone_number(value):
            # log_msg(logFile, f"{value}: Встановлюємо червоний колір тла")
            value_item.setBackground(Qt.red)
        self.metadata_model.appendRow([key_item, value_item])

        # CadastralQuarterNumber
        # log_msg(logFile, "Додаємо дані і tooltip кадастрового кварталу")
        cadastral_quarter_number = xmlTree.find(".//InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/CadastralQuarterNumber")
        if cadastral_quarter_number is not None:
            value = cadastral_quarter_number.text.strip() if cadastral_quarter_number.text else ""
        else:
            value = ""
        # log_msg(logFile, f"cadastral_quarter_number = '{cadastral_quarter_number}'")
        # log_msg(logFile, f"value = '{value}'")
        key_item = QStandardItem("Номер кадастрового кварталу")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
        key_item.setToolTip(
            "<b>Номер кадастрового кварталу</b><br>"
            "Номер кадастрового кварталу в межах кадастрової зони<br>"
            "Значення '000' здебільшого означає, що квартал знаходиться<br>"
            "за межами населеного пункту"
        )
        full_path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/CadastralQuarterNumber"
        key_item.setData(full_path, Qt.UserRole)  # Зберігаємо повний шлях
        value_item = QStandardItem(value)
        value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)  # Дозволяємо редагування
        # Перевірка на відповідність масці
        # log_msg(logFile, f"Перевірка номера кадастрового кварталу")
        if not self.validate_cad_quarter_number(value):
            # log_msg(logFile, f"{value}: Встановлюємо червоний колір тла")
            value_item.setBackground(Qt.red)
        self.metadata_model.appendRow([key_item, value_item])

        # ПІБ керівника виконавчої влади
        # Пошук елементів ПІБ
        last_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/LastName")
        first_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/FirstName")
        middle_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead/MiddleName")
        # Отримання значень або порожніх рядків
        last_name_value = last_name.text.strip() if last_name is not None and last_name.text else ""
        first_name_value = first_name.text.strip() if first_name is not None and first_name.text else ""
        middle_name_value = middle_name.text.strip() if middle_name is not None and middle_name.text else ""
        # Формування ПІБ
        full_name = f"{last_name_value} {first_name_value} {middle_name_value}".strip()
        # Додавання до таблиці
        key_item = QStandardItem("ПІБ керівника виконавчої влади")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
        key_item.setToolTip(
            "Формат: <Прізвище Ім'я По батькові>\n"
            "Приклад: Іваненко Петро Андрійович\n"
            "MiddleName (По батькові) необов'язковий"
        )
        full_path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead"
        key_item.setData(full_path, Qt.UserRole)
        value_item = QStandardItem(full_name)
        value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)  # Дозволяємо редагування
        # Перевірка на відповідність масці
        if not self.validate_full_name(full_name):
            value_item.setBackground(Qt.red)
        self.metadata_model.appendRow([key_item, value_item])

        # ПІБ начальника територіального органу земельних ресурсів
        # Пошук елементів ПІБ
        last_name   = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/DKZRHead/LastName")
        first_name  = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/DKZRHead/FirstName")
        middle_name = xmlTree.find(".//CadastralQuarterInfo/RegionalContacts/DKZRHead/MiddleName")
        # Отримання значень або порожніх рядків
        last_name_value = last_name.text.strip() if last_name is not None and last_name.text else ""
        first_name_value = first_name.text.strip() if first_name is not None and first_name.text else ""
        middle_name_value = middle_name.text.strip() if middle_name is not None and middle_name.text else ""
        # Формування ПІБ
        full_name = f"{last_name_value} {first_name_value} {middle_name_value}".strip()
        # Додавання до таблиці
        key_item = QStandardItem("ПІБ начальника ТО ЗР")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # Забороняємо редагування
        key_item.setToolTip(
            "ПІБ начальника територіального органу земельних ресурсів\n"
            "Формат: <Прізвище Ім'я По батькові>\n"
            "Приклад: Іваненко Петро Андрійович\n"
            "MiddleName (По батькові) необов'язковий"
        )
        full_path = "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead"
        key_item.setData(full_path, Qt.UserRole)
        value_item = QStandardItem(full_name)
        value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)  # Дозволяємо редагування
        # Перевірка на відповідність масці
        if not self.validate_full_name(full_name):
            value_item.setBackground(Qt.red)
        self.metadata_model.appendRow([key_item, value_item])




        self.resizeColumnToContents(0)

        # log_msg(logFile, "Після заповнення моделі встановлення обробника зміни даних")
        self.metadata_model.itemChanged.connect(self.on_item_changed_metadata)
    def on_item_changed_metadata(self, value_item): # Вибір елемента дерева відповідного рядку таблиці 
        """ Обробка події зміни даних таблиці
        """
        row = value_item.row()
        col = value_item.column()
        # log_msg(logFile, f"index({row}, {col})")
        key_item = self.metadata_model.item(row, 0)
        # Отримуємо шлях із UserRole
        path = key_item.data(Qt.UserRole)
        # log_msg(logFile, f"path = '{path}'")
        if not path:
            log_msg(logFile, "Шлях елемента таблиці дорівнює None.")
            return
        value = value_item.text()

        # Змінюється "Дата формування файлу"
        if path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileDate":
            self.parent.treeViewXML.update_file_date_tree(path, value)
        # Змінюється "Унікальний ідентифікатор файлу"
        if path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileGUID":
            self.parent.treeViewXML.update_file_GUID_tree(path, value)
        # Змінюється "Версія формату обмінного файлу"
        if path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FormatVersion":
            self.parent.treeViewXML.update_FormatVersion_tree(path, value)
        # Змінюється "Найменування підрозділу Центру ДЗК"
        if path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverName":
            self.parent.treeViewXML.update_ReceiverName_tree(path, value)
        # Змінюється "Ідентифікатор підрозділу Центру ДЗК"
        if path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverIdentifier":
            self.parent.treeViewXML.update_ReceiverIdentifier_tree(path, value)
        # Змінюється "Назва програмного забезпечення"
        if path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/Software":
            self.parent.treeViewXML.update_Software_tree(path, value)
        # Змінюється "Версія програмного забезпечення"
        if path == "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/SoftwareVersion":
            self.parent.treeViewXML.update_SoftwareVersion_tree(path, value)
        # Змінюється "Система координат"
        if path == "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/CoordinateSystem":
            self.parent.treeViewXML.update_coordinate_system_tree(path, value)
            return
        # Змінюється "Система висот"
        if path == "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/HeightSystem":
            self.parent.treeViewXML.update_height_system_tree(value)
            return
        # Змінюється "Одиниця виміру довжини"
        if path == "UkrainianCadastralExchangeFile/InfoPart/MetricInfo/MeasurementUnit":
            self.parent.treeViewXML.update_measurement_unit_tree(value)
            return
        # Якщо змінюється "Номер кадастрової зони"
        if path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralZoneNumber":
            self.parent.treeViewXML.update_cadastral_zone_number_tree(value)
            return
        # Якщо змінюється "Номер кадастрового кварталу"
        if path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/CadastralQuarterNumber":
            # self.parent.treeViewXML.update_cadastral_quarter_tree(value)
            self.parent.treeViewXML.update_cadastral_quarter_tree(value)
            return
        # Якщо змінюється ПІБ керівника влади
        if path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/LocalAuthorityHead":
            self.parent.treeViewXML.update_local_authority_head_tree(value)
            return
        # Якщо змінюється ПІБ керівника ТО ЗР
        if path == "UkrainianCadastralExchangeFile/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts/DKZRHead":
            self.parent.treeViewXML.update_DKZRHead_tree(value)
            return



        index = self.parent.find_element_index(path=path)
        if index.isValid():
            tree_item = self.model.itemFromIndex(index)
            if tree_item:
                # Оновлюємо текст у колонці 1 (значення вузла)
                tree_item.parent().child(tree_item.row(), 1).setText(value)
                log_msg(logFile, f"Оновлено значення у дереві: {path} -> {value}")
        else:
            # log_msg(logFile, f"Елемент не знайдено у дереві: {path}")
            pass
    def validate_cad_zone_number(self, value):
        """
        Перевіряє значення на відповідність масці "9999999999:99".
        """
        # log_msg(logFile, "9999999999:99")
        import re
        pattern = r"^\d{10}:\d{2}$"
        return bool(re.match(pattern, value))
    def validate_cad_quarter_number(self, value):
        """
        Перевіряє значення на відповідність масці "999".
        """
        # log_msg(logFile, "999")
        import re
        pattern = r"^\d{3}$"
        return bool(re.match(pattern, value))
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
        log_msg(logFile, "Обробляє систему висот з XML і повертає значення для таблиці")

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
    def generate_coordinate_system_xml(self):
        """
        Формує XML для системи координат на основі значень таблиці.
        """
        log_msg(logFile)
        root = ET.Element("CoordinateSystem")

        for row in range(self.model.rowCount()):
            key_item = self.model.item(row, 0)
            value_item = self.model.item(row, 1)

            if key_item.text() == "CoordinateSystem":
                value = value_item.text()
                if "Local" in value:
                    # Якщо Local, додаємо реєстраційний номер
                    reg_number = value.split("(")[-1].strip(")")
                    ET.SubElement(root, "Local").text = reg_number
                elif "SC63" in value:
                    # Якщо SC63, додаємо відповідну зону
                    zone = value.split(",")[-1]
                    ET.SubElement(root, "SC63").append(ET.Element(zone))
                else:
                    # Інші системи координат
                    ET.SubElement(root, value)

        return root
