# -*- coding: utf-8 -*-
"""Таблиця даних земельної ділянки"""
import os
import uuid

from datetime import datetime
from lxml import etree

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtCore import QModelIndex

from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QMenu
from qgis.PyQt.QtWidgets import QTabWidget

from qgis.PyQt.QtWidgets import QTableView
from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QStandardItemModel
from qgis.PyQt.QtCore import pyqtSignal

from .date_dialog import DateInputDialog

from .common import logFile
from .common import log_msg
from .common import log_calls
from .common import config
from .common import config_docs
from .common import connector

from .person import TableViewNaturalPerson
from .entity import TableViewLegalEntity

class TableViewParcel(QTableView):
    """
        Клас таблиці для відображення та роботи з даними земельної ділянки.
    """

    # Сигнал для оновлення даних
    parcelChangedSignal = pyqtSignal(str, str)  # Сигнал для оновлення даних

    # Клас TableViewParcel успадковує клас QTableView
    # заповнює таблицю Ділянка основними даними земельної ділянки
    # для даних, які можуть бути в різних кількостях від 0 до нескінченності
    # за необхідності створюються додаткові вкладки для відображення даних


    def __init__(self, parent=None):

        super().__init__(parent)

        # Явно зберігаємо батьківський об'єкт
        self.parent = parent
        self.parcel_block_change_flag = False
        # log_calls(logFile, f"🚩 {self.parcel_block_change_flag}")

        # Змінити висоту горизонтального заголовка
        self.horizontalHeader().setFixedHeight(30)
        self.verticalHeader().setDefaultSectionSize(30)

        self.items_model = QStandardItemModel()
        self.setModel(self.items_model)
        self.items_model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        self.empty_elents = []
        self.docs_dict = dict(config_docs['DocsList'])
        self.docs_tips = dict(config_docs['DocsTips'])

        # Підключення обробника правого кліку
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        # Підключення обробника змін даних у комірках
        #self.items_model.itemChanged.connect(self.parcel_item_changed)
        connector.connect(self.items_model, "itemChanged", self.parcel_item_changed)


    def parcel_item_changed(self, cell):
        """ Обробка події зміни комірок QStandardcellModel

            Визначає full_path, value комірки де змінились дані і
            формує сигнал dataChangedInparcel = pyqtSignal(str, str)
        """

        log_msg(logFile, f"{cell.text()}")
        log_msg(logFile, f"parcel_block_change_flag = {self.parcel_block_change_flag}")
        if self.parcel_block_change_flag:
            log_msg(logFile, f"parcel_block_change_flag = {self.parcel_block_change_flag} - пропускаємо оновлення")
            return

        log_msg(logFile, f"встановлюємо parcel_block_change_flag для блокування змін за межами функції і виконуємо оновлення")
        self.parcel_block_change_flag = True

        try:
            value = cell.text()
            full_path = cell.data(Qt.UserRole)
            tag = full_path.split("/")[-1]
            log_msg(logFile,f"тег комірки: {tag}")
            log_msg(logFile, "Пвернення з функції tree_XXXXX_update()")
        finally:
            self.parcel_block_change_flag = False
            log_msg(logFile, f"Скидання флагу блокування змін parcel_block_change_flag = {self.parcel_block_change_flag}")
            pass


    def add_region(self, xml_tree, path):

        element = xml_tree.find(".//ParcelLocationInfo/Region")
        if element is not None:
            value = element.text
            key_item = QStandardItem("Регіон")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            key_item.setToolTip(
                "Місцезнаходження земельної ділянки<br>"
                "<b>Область або місто республіканського підпорядкування) </b> <br>"
                "Елемент Region"
            )
            value_item = QStandardItem(value)
            value_item.setData(path, Qt.UserRole)
            self.items_model.appendRow([key_item, value_item])


    def add_settlement(self, xml_tree, path):

        element = xml_tree.find(".//ParcelLocationInfo/Settlement")
        if element is not None:
            value = element.text
            key_item = QStandardItem("Назва населеного пункту")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            key_item.setToolTip(
                "Місцезнаходження земельної ділянки<br>"
                "<b>Назва населеного пункту</b> <br>"
                "Елемент Settlement<br>"
                "Необов'язковий для XSD версії 0.7<br>"
            )
            value_item = QStandardItem(value)
            value_item.setData(path, Qt.UserRole)
            key_item.setData(path, Qt.UserRole)
            self.items_model.appendRow([key_item, value_item])
    def add_district(self, xml_tree, path):
        element = xml_tree.find(".//ParcelLocationInfo/District")
        if element is not None:
            value = element.text
            key_item = QStandardItem("Назва району")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            key_item.setToolTip(
                "Місцезнаходження земельної ділянки<br>"
                "<b>Назва району</b> <br>"
                "Елемент District<br>"
                "Необов'язковий для XSD версії 0.7<br>"
            )
            value_item = QStandardItem(value)
            value_item.setData(path, Qt.UserRole)
            key_item.setData(path, Qt.UserRole)
            self.items_model.appendRow([key_item, value_item])
    def add_parcel_location(self, xml_tree, path):
        element = xml_tree.find(".//ParcelLocationInfo/ParcelLocation")
        if element is not None:
            value = "За межами населеного пункту" if element.find("Rural") is not None else "У межах населеного пункту"
            where = "Rural" if element.find("Rural") is not None else "Urban"
            key_item = QStandardItem("Розташування ділянки")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            key_item.setToolTip(
                "Місцезнаходження земельної ділянки<br>"
                "<b>Відношення до населеного пункту</b> <br>"
                "в межах чи за межами населеного пункту<br>"
                "Елемент ParcelLocation<br>"
            )
            value_item = QStandardItem(value)
            value_item.setData(where, Qt.UserRole)
            key_item.setData(path, Qt.UserRole)
            self.items_model.appendRow([key_item, value_item])
    def add_street_type(self, xml_tree, path):
        element = xml_tree.find(".//ParcelAddress/StreetType")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Тип проїзду")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Тип проїзду (вулиця, проспект, провулок,</b> <br>"
            "урочище, тупик, острів...)<br>"
            "де розташована земельна ділянка<br>"
            "(можна не вказувати, якщо ділянка за межами населеного пункту)"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_street_name(self, xml_tree, path):
        element = xml_tree.find(".//ParcelAddress/StreetName")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Назва вулиці")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Назва вулиці</b> <br>"
            "(можна не вказувати, якщо ділянка за межами населеного пункту)"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_building(self, xml_tree, path):
        element = xml_tree.find(".//ParcelAddress/Building")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Номер будинку")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Номер будинку</b> <br>"
            "(можна не вказувати, якщо ділянка за межами населеного пункту)"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_block(self, xml_tree, path):
        element = xml_tree.find(".//ParcelAddress/Block")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Номер корпусу")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Номер корпусу</b> <br>"
            "(можна не вказувати)"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_additional_info(self, xml_tree, path):
        element = xml_tree.find(".//ParcelLocationInfo/AdditionalInfoBlock/AdditionalInfo")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Додаткова інформація")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Додаткова інформація</b> <br>"
            "(не обов'язково)"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_category(self, xml_tree, path):
        element = xml_tree.find(".//CategoryPurposeInfo/Category")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Категорія земель")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Категорія земель</b> <br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_purpose(self, xml_tree, path):
        element = xml_tree.find(".//CategoryPurposeInfo/Purpose")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Цільове призначення")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Цільове призначення (використання) земельної ділянки</b> <br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_use(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент Use з xml_tree """
        # log_msg(logFile, f"path = {path}")
        element = xml_tree.find(".//CategoryPurposeInfo/Use")
        # log_msg(logFile, f"element = {element}")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        # log_msg(logFile, f"Use value = {value}")
        key_item = QStandardItem("Цільове призначення")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Цільове призначення (використання) згідно із документом,</b><br>"
            "що є підставою для виникнення права<br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_code(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент Code з xml_tree """
        # log_msg(logFile, f"path = {path}")
        element = xml_tree.find(".//OwnershipInfo/Code")
        # log_msg(logFile, f"element = {element}")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        # log_msg(logFile, f"value = {value}")
        key_item = QStandardItem("Код форми власності")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Код форми власності на земельну ділянку</b><br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_description(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент Description з xml_tree """
        # log_msg(logFile, f"path = {path}")
        element = xml_tree.find(".//ParcelMetricInfo/Description")
        # log_msg(logFile, f"element = {element}")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        # log_msg(logFile, f"value = {value}")
        key_item = QStandardItem("Опис земельної ділянки")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Опис земельної ділянки</b><br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_measurement_unit(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент MeasurementUnit з xml_tree """
        element = xml_tree.find(".//Area/MeasurementUnit")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Одиниця виміру")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Одиниця виміру площі земельної ділянки</b><br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_size(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент Size з xml_tree """
        element = xml_tree.find(".//Area/Size")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Розмір")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Розмір площі земельної ділянки</b><br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_determination_method(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент DeterminationMethod з xml_tree """
        element = xml_tree.find(".//Area/DeterminationMethod")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Метод визначення")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Метод визначення площі земельної ділянки</b><br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
        self.resizeColumnToContents(0)
    def add_determination_method(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент DeterminationMethod з xml_tree """
        element = xml_tree.find(".//Area/DeterminationMethod")
        if element is not None:
            if element.find("ExhangeFileCoordinates") is not None:
                value = "За координатами обмінного файлу"
            elif element.find("DocExch") is not None:
                value = "Згідно із правовстановлювальним документом"
            elif element.find("Calculation") is not None:
                value = "Переобчислення"
            else:
                value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Метод визначення")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Метод визначення площі земельної ділянки</b><br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_error(self, xml_tree, path):
        """ Додає до таблиці інформацію про елемент Error з xml_tree """
        element = xml_tree.find(".//ParcelMetricInfo/Error")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Помилка")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip(
            "<b>Помилка</b><br>"
        )
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_state_act_type(self, xml_tree, path):
        element = xml_tree.find(".//StateActInfo/StateActType")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Тип державного акту")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Тип державного акту</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_state_act_series(self, xml_tree, path):
        element = xml_tree.find(".//StateActInfo/StateActForm/Series")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Серія державного акту")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Серія державного акту</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_state_act_number(self, xml_tree, path):
        element = xml_tree.find(".//StateActInfo/StateActForm/Number")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Номер державного акту")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Номер державного акту</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_registration_book_number(self, xml_tree, path):
        element = xml_tree.find(".//StateActRegistrationInfo/RegistrationBookNumber")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Номер реєстраційної книги")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Номер реєстраційної книги</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_section_number(self, xml_tree, path):
        element = xml_tree.find(".//StateActRegistrationInfo/SectionNumber")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Номер розділу")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Номер розділу</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_registration_number(self, xml_tree, path):
        element = xml_tree.find(".//StateActRegistrationInfo/RegistrationNumber")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Реєстраційний номер")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Реєстраційний номер</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_registration_date(self, xml_tree, path):
        element = xml_tree.find(".//StateActRegistrationInfo/RegistrationDate")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Дата реєстрації")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Дата реєстрації</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_signed_by_name(self, xml_tree, path):
        elements = xml_tree.findall(".//SignedByName")
        for i, element in enumerate(elements):
            last_name = element.find("LastName").text if element.find("LastName") is not None else ""
            first_name = element.find("FirstName").text if element.find("FirstName") is not None else ""
            middle_name = element.find("MiddleName").text if element.find("MiddleName") is not None else ""
            full_name = f"{last_name} {first_name} {middle_name}".strip()
            
            key_item = QStandardItem("ПІБ особи, яка підписала держаний акт")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if i == 0:
                key_item.setToolTip("<b>ПІБ представника органу Дежкомзему,</b><br>який підписав державний акт")
            else:
                key_item.setToolTip("<b>ПІБ представника місцевої влади,</b><br>який підписав державний акт")
            value_item = QStandardItem(full_name)
            value_item.setData(path, Qt.UserRole)
            key_item.setData(path, Qt.UserRole)
            self.items_model.appendRow([key_item, value_item])
    def add_delivery_date(self, xml_tree, path):
        element = xml_tree.find(".//StateActInfo/DeliveryDate")
        if element is not None:
            value = element.text
        else:
            self.empty_elents.append(path)
            value = ""
        key_item = QStandardItem("Дата видачі")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        key_item.setToolTip("<b>Дата видачі державного акту</b><br>")
        value_item = QStandardItem(value)
        value_item.setData(path, Qt.UserRole)
        key_item.setData(path, Qt.UserRole)
        self.items_model.appendRow([key_item, value_item])
    def add_legal_mode_info(self, xml_tree, path):
        """
        Adds legal mode information to the provided XML tree and updates the UI with the relevant data.
        Parameters:
        xml_tree (ElementTree): The XML tree containing the legal mode information.
        path (str): The file path associated with the XML tree.
        This method performs the following steps:
        1. Finds the "LegalModeInfo" element in the XML tree.
        2. If found, creates a new tab in the QTabWidget for displaying legal mode information.
        3. Populates the tab with the legal mode type, start date, and expiration date.
        4. Iterates through users and grantors, adding tabs for each natural person or legal entity found.
        The tabs are labeled and tooltips are set to provide additional information about the legal mode and users/grantors.
        """
        # log_msg(logFile, f"Start")
        element = xml_tree.find(".//LegalModeInfo")
        # log_msg(logFile, f"element.tag = {element.tag}")
        if element is not None:
            tab_widget = self.parent.findChild(QTabWidget, "tabWidget")
            if not tab_widget:
                log_msg(logFile, "❌ Не знайдено QTabWidget у xml_uaDockWidget")
                return

            legal_mode_tab = QTableView(self.parent)
            legal_mode_model = QStandardItemModel()
            legal_mode_tab.setModel(legal_mode_model)
            legal_mode_model.setHorizontalHeaderLabels(["Елемент", "Значення"])
    
            legal_mode_type = element.find("LegalModeType")
            start_date = element.find("Duration/StartDate")
            # Логуємо start_date
            # log_msg(logFile, f"start_date = {start_date.tag}")
            expiration_date = element.find("Duration/ExpirationDate")
            # Логуємо expiration_date
            # log_msg(logFile, f"expiration_date = {expiration_date.tag}")
            # expiration_date = None
    
            if legal_mode_type is not None:
                key_item = QStandardItem("Тип користування")
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(legal_mode_type.text)
                value_item.setData(path, Qt.UserRole)
                legal_mode_model.appendRow([key_item, value_item])
    
            if start_date is not None:
                key_item = QStandardItem("Дата початку")
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(start_date.text)
                value_item.setData(path, Qt.UserRole)
                legal_mode_model.appendRow([key_item, value_item])
    
            if expiration_date is not None:
                key_item = QStandardItem("Дата закінчення")
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(expiration_date.text)
                value_item.setData(path, Qt.UserRole)
                legal_mode_model.appendRow([key_item, value_item])
    
            index = tab_widget.addTab(legal_mode_tab, "Користування")
            tab_widget.setTabToolTip(index, "Користування земельною ділянкою")
    
            users = element.findall(".//Grantee")
            for user in users:
                # auth_element = user.find("Authentication")
                # log_msg(logFile, f"auth_element.tag = {auth_element.tag}")
                # if auth_element is not None:
                    if user.find("NaturalPerson") is not None:
                        person = user.find("NaturalPerson")
                        full_name_node = person.find("FullName")
                        if full_name_node is not None:
                            last_name = full_name_node.find("LastName").text if full_name_node.find("LastName") is not None else ""
                            first_name = full_name_node.find("FirstName").text if full_name_node.find("FirstName") is not None else ""
                            middle_name = full_name_node.find("MiddleName").text if full_name_node.find("MiddleName") is not None else ""
                            full_name = f"{last_name} {first_name[:1]}.{middle_name[:1]}.".strip()
                        else:
                            full_name = "Без імені"
    
                        tab_name = full_name
                        new_tab = TableViewNaturalPerson(self.parent)
                        new_tab.populate_natural_person(xml_tree, user, person)
                        index = tab_widget.addTab(new_tab, tab_name)
                        tab_widget.setTabToolTip(index, "Користувач земельної ділянки")
    
                    elif user.find("LegalEntity") is not None:
                        entity = user.find("LegalEntity")
                        entity_name = entity.find("Name").text if entity.find("Name") is not None else "Без назви"
    
                        tab_name = entity_name
                        new_tab = TableViewLegalEntity(self.parent)
                        new_tab.populate_legal_entity(xml_tree, ".//Grantee/LegalEntity")
                        index = tab_widget.addTab(new_tab, tab_name)
                        tab_widget.setTabToolTip(index, "Користувач земельної ділянки")
    
            grantors = element.findall(".//Grantor")
            for grantor in grantors:
                # auth_element = grantor.find("Authentication")
                # if auth_element is not None:
                # log_msg(logFile, f"Кількість надавачів: {len(grantors)}")
                if grantor.find("NaturalPerson") is not None:
                    log_msg(logFile, "Знайдено надавач NaturalPerson")
                    person = grantor.find("NaturalPerson")
                    full_name_node = person.find("FullName")
                    if full_name_node is not None:
                        last_name = full_name_node.find("LastName").text if full_name_node.find("LastName") is not None else ""
                        first_name = full_name_node.find("FirstName").text if full_name_node.find("FirstName") is not None else ""
                        middle_name = full_name_node.find("MiddleName").text if full_name_node.find("MiddleName") is not None else ""
                        full_name = f"{last_name} {first_name[:1]}.{middle_name[:1]}.".strip()
                    else:
                        full_name = "Без імені"
    
                    tab_name = full_name
                    new_tab = TableViewNaturalPerson(self.parent)
                    new_tab.populate_natural_person(xml_tree, grantor, person)
                    index = tab_widget.addTab(new_tab, tab_name)
                    tab_widget.setTabToolTip(index, "Надавач земельної ділянки")

                elif grantor.find("LegalEntity") is not None:
                    # log_msg(logFile, "Знайдено надавач LegalEntity")
                    entity = grantor.find("LegalEntity")
                    entity_name = entity.find("Name").text if entity.find("Name") is not None else "Без назви"
                    # log_msg(logFile, f"entity_name = {entity_name}")
                    tab_name = entity_name
                    new_tab = TableViewLegalEntity(self.parent)
                    new_tab.populate_legal_entity(xml_tree, ".//Grantor/LegalEntity")
                    index = tab_widget.addTab(new_tab, tab_name)
                    tab_widget.setTabToolTip(index, "Надавач земельної ділянки")    
    def fill_parcel_data(self, xmlTree):
        """ Заповнює таблицю даними, встановлює підказки
            Параметри:
                xmlTree: завантажене дерево xml
        """
        # log_msg(logFile, f"xmlTree = {xmlTree}")
        self.items_model.removeRows(0, self.items_model.rowCount())
        paths = config.get("Parcel", "paths").splitlines()
        self.empty_elents = []
        for path in paths:
            tag = path.split("/")[-1]
            # log_msg(logFile, f"tag = {tag}")
            if tag == "Region": 
                self.add_region(xmlTree, path)
                continue
            if tag == "Settlement":
                self.add_settlement(xmlTree, path)
                continue
            if tag == "District":
                self.add_district(xmlTree, path)
                continue
            if tag == "ParcelLocation":
                self.add_parcel_location(xmlTree, path)
                continue
            if tag == "StreetType":
                self.add_street_type(xmlTree, path)
                continue
            if tag == "StreetName":
                self.add_street_name(xmlTree, path)
                continue
            if tag == "Building":
                self.add_building(xmlTree, path)
                continue
            if tag == "Block":
                self.add_block(xmlTree, path)
                continue
            if tag == "AdditionalInfo":
                # log_msg(logFile, f"AdditionalInfo path = {path}")
                self.add_additional_info(xmlTree, path)
                continue
            if tag == "Category":
                self.add_category(xmlTree, path)
                continue
            if tag == "Purpose":
                self.add_purpose(xmlTree, path)
                continue
            if tag == "Use":
                self.add_use(xmlTree, path)
                continue
            if tag == "Code":
                self.add_code(xmlTree, path)
                continue
            if tag == "Description":
                self.add_description(xmlTree, path)
                continue
            if tag == "MeasurementUnit":
                self.add_measurement_unit(xmlTree, path)
                continue
            if tag == "Size":
                self.add_size(xmlTree, path)
                continue
            if tag == "DeterminationMethod":
                self.add_determination_method(xmlTree, path)
                continue
            if tag == "Error":
                self.add_error(xmlTree, path)
                continue
            if tag == "StateActType":
                self.add_state_act_type(xmlTree, path)
                continue
            if tag == "Series":
                self.add_state_act_series(xmlTree, path)
                continue
            if tag == "Number":
                self.add_state_act_number(xmlTree, path)
                continue
            if tag == "RegistrationBookNumber":
                self.add_registration_book_number(xmlTree, path)
                continue
            if tag == "SectionNumber":
                self.add_section_number(xmlTree, path)
                continue
            if tag == "RegistrationNumber":
                self.add_registration_number(xmlTree, path)
                continue
            if tag == "RegistrationDate":
                self.add_registration_date(xmlTree, path)
                continue
            if tag == "LastName":
                self.add_signed_by_name(xmlTree, path)
                continue
            if tag == "DeliveryDate":
                self.add_delivery_date(xmlTree, path)
                continue
            if tag == "Proprietors":
                proprietors = xmlTree.findall(".//Proprietors/ProprietorInfo")
                tab_widget = self.parent.findChild(QTabWidget, "tabWidget")

                if not tab_widget:
                    log_msg(logFile, "❌ Не знайдено QTabWidget у xml_uaDockWidget")
                else:
                    existing_tabs = [tab_widget.tabText(i) for i in range(tab_widget.count())]

                    for proprietor in proprietors:
                        auth_element = proprietor.find("Authentication")
                        if auth_element is not None:
                            if auth_element.find("NaturalPerson") is not None:
                                person = auth_element.find("NaturalPerson")
                                full_name_node = person.find("FullName")
                                if full_name_node is not None:
                                    last_name = full_name_node.find("LastName").text if full_name_node.find("LastName") is not None else ""
                                    first_name = full_name_node.find("FirstName").text if full_name_node.find("FirstName") is not None else ""
                                    middle_name = full_name_node.find("MiddleName").text if full_name_node.find("MiddleName") is not None else ""
                                    full_name = f"{last_name} {first_name[:1]}.{middle_name[:1]}.".strip()
                                else:
                                    full_name = "Без імені"

                                tab_name = full_name if full_name not in existing_tabs else f"{full_name} ({existing_tabs.count(full_name) + 1})"
                                new_tab = TableViewNaturalPerson(self.parent)
                                # person -> .//ProprietorInfo/Authentication/NaturalPerson
                                new_tab.populate_natural_person(xmlTree, proprietor, person)
                                index = tab_widget.addTab(new_tab, tab_name)
                                tab_widget.setTabToolTip(index, f"Власник земельної ділянки")
                                # log_msg(logFile, f"✔️ Сформовано ім'я вкладки: {tab_name}")

                            elif auth_element.find("LegalEntity") is not None:
                                entity = auth_element.find("LegalEntity")
                                entity_name = entity.find("Name").text if entity.find("Name") is not None else "Без назви"

                                tab_name = entity_name if entity_name not in existing_tabs else f"{entity_name} ({existing_tabs.count(entity_name) + 1})"
                                new_tab = TableViewLegalEntity(self.parent)
                                new_tab.populate_legal_entity(xmlTree, ".//ProprietorInfo/Authentication/LegalEntity")
                                index = tab_widget.addTab(new_tab, tab_name)
                                tab_widget.setTabToolTip(index, f"Власник земельної ділянки")
                                # log_msg(logFile, f"✔️ Сформовано ім'я вкладки: {tab_name}")
                continue
            if tag == "LegalModeInfo":
                self.add_legal_mode_info(xmlTree, path)
                continue
            if tag == "TechnicalDocumentationInfo":
                self.add_tech_documentation(xmlTree, path)
                continue
        self.resizeColumnToContents(0)
    def add_tech_documentation(self, xml_tree, path):
        """
        Adds technical documentation information to the provided XML tree and updates the UI with the relevant data.
        Parameters:
        xml_tree (ElementTree): The XML tree containing the technical documentation information.
        path (str): The file path associated with the XML tree.
        """
        element = xml_tree.find(".//TechnicalDocumentationInfo")
        if element is not None:
            tab_widget = self.parent.findChild(QTabWidget, "tabWidget")
            if not tab_widget:
                log_msg(logFile, "❌ Не знайдено QTabWidget у xml_uaDockWidget")
                return
            tech_doc_tab = QTableView(self.parent)
            tech_doc_model = QStandardItemModel()
            tech_doc_tab.setModel(tech_doc_model)
            tech_doc_model.setHorizontalHeaderLabels(["Елемент", "Значення"])
            fields = [
                ("DocumentationType", "Тип документації"),
                ("DraftingDate", "Дата складання"),
                ("RegistrationData/BookNumber", "Номер книги реєстрації"),
                ("RegistrationData/RegistrationDate", "Дата реєстрації"),
                ("RegistrationData/RegistrationAuthority", "Орган реєстрації"),
                ("RegistrationCard/BookNumber", "Номер реєстраційної картки"),
                ("RegistrationCard/IssuanceDate", "Дата видачі"),
                ("Expertise/ExpertiseRequired", "Потреба в експертизі"),
                ("Expertise/ExpertiseAuthority", "Орган експертизи"),
                ("Expertise/ExpertOpinion", "Висновок експертизи"),
                ("Expertise/ExpertiseDate", "Дата експертизи"),
                ("Expertise/ExpertiseNumber", "Номер експертизи"),
                ("ApprovalInfo/ApprovalAuthority", "Орган затвердження"),
                ("ApprovalInfo/ApprovalDate", "Дата затвердження"),
                ("ApprovalInfo/ApprovalNumber", "Номер затвердження"),
                ("ApprovalInfo/ApprovalDocument", "Документ затвердження"),
                ("ApprovalActDate", "Дата акту затвердження")
            ]
            for field, label in fields:
                sub_element = element.find(f".//{field}")
                value = sub_element.text if sub_element is not None else ""
                key_item = QStandardItem(label)
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(value)
                value_item.setData(path, Qt.UserRole)
                key_item.setData(path, Qt.UserRole)
                tech_doc_model.appendRow([key_item, value_item])
            index = tab_widget.addTab(tech_doc_tab, "Документація")
            tab_widget.setTabToolTip(index, "<b>Відомості про документацію із землеустрою</b><br>та проходження державної експертизи")
            # Add Document List Tab
            doc_list_tab = QTableView(self.parent)
            doc_list_model = QStandardItemModel()
            doc_list_tab.setModel(doc_list_model)
            doc_list_model.setHorizontalHeaderLabels(["Документ", "Наявність"])
            for doc_code, doc_name in self.docs_dict.items():
                key_item = QStandardItem(doc_name)
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                key_item.setToolTip(self.docs_tips.get(doc_code, ""))
                value_item = QStandardItem()
                value_item.setCheckable(True)
                # Check if the element with the specified doc_code exists in the XML tree
                exists = xml_tree.xpath(f".//DocumentList[text()='{doc_code}']")
                value_item.setCheckState(Qt.Checked if exists else Qt.Unchecked)
                value_item.setData(path, Qt.UserRole)
                key_item.setData(path, Qt.UserRole)
                doc_list_model.appendRow([key_item, value_item])
            index = tab_widget.addTab(doc_list_tab, "Список документів")
            tab_widget.setTabToolTip(index, "Список документів")
            tech_doc_tab.horizontalHeader().setStretchLastSection(True)
            tech_doc_tab.resizeColumnToContents(0)
            doc_list_tab.horizontalHeader().setStretchLastSection(True)
            doc_list_tab.resizeColumnToContents(0)