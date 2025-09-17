# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import Qt

from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QStandardItemModel

from qgis.PyQt.QtWidgets import QTableView, QHeaderView

from .common import log_msg
from .common import log_msg
from .common import logFile



class TableViewLegalEntity(QTableView):
    """
        Клас таблиці для відображення та роботи з даними юридичної особи.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items_model = QStandardItemModel()
        self.setModel(self.items_model)
        self.items_model.setHorizontalHeaderLabels(["Елемент", "Значення"])
        self.empty_elements = []
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)


    def populate_legal_entity(self, xml_tree, entity):
        # log_msg(logFile, f"start")
        self.items_model.removeRows(0, self.items_model.rowCount())
        elements = xml_tree.findall(entity)
        # log_msg(logFile, f"entity = {entity}")
        # log_msg(logFile, f"elements = {elements}")
        # log_msg(logFile, f"num of elements {len(elements)}")
        
        for element in elements:
            self.add_name(element)
            self.add_edrpou(element)
            self.add_address(element)
            self.add_additional_info(element)

        self.resizeColumnToContents(0)

    def add_name(self, element):
        name = element.find("Name")
        value = name.text if name is not None else ""
        key_item = QStandardItem("Назва юридичної особи")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        value_item = QStandardItem(value)
        self.items_model.appendRow([key_item, value_item])
    def add_edrpou(self, element):
        edrpou = element.find("EDRPOU")
        value = edrpou.text if edrpou is not None else ""
        key_item = QStandardItem("Код ЄДРПОУ")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        value_item = QStandardItem(value)
        self.items_model.appendRow([key_item, value_item])
    def add_address(self, element):
        address = element.find("Address")
        if address is not None:
            country = address.find("Country").text if address.find("Country") is not None else ""
            zip_code = address.find("ZIP").text if address.find("ZIP") is not None else ""
            region = address.find("Region").text if address.find("Region") is not None else ""
            district = address.find("District").text if address.find("District") is not None else ""
            settlement = address.find("Settlement").text if address.find("Settlement") is not None else ""
            street = address.find("Street").text if address.find("Street") is not None else ""
            building = address.find("Building").text if address.find("Building") is not None else ""
            block = address.find("Block").text if address.find("Block") is not None else ""
            building_unit = address.find("BuildingUnit").text if address.find("BuildingUnit") is not None else ""
            value = f"{country} {zip_code} {region} {district} {settlement} {street} {building} {block} {building_unit}".strip()
            key_item = QStandardItem("Адреса")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(value)
            self.items_model.appendRow([key_item, value_item])
    def add_address(self, element):
        address = element.find("Address")
        if address is not None:
            country = address.find("Country").text if address.find("Country") is not None else ""
            zip_code = address.find("ZIP").text if address.find("ZIP") is not None else ""
            region = address.find("Region").text if address.find("Region") is not None else ""
            district = address.find("District").text if address.find("District") is not None else ""
            settlement = address.find("Settlement").text if address.find("Settlement") is not None else ""
            street = address.find("Street").text if address.find("Street") is not None else ""
            building = address.find("Building").text if address.find("Building") is not None else ""
            block = address.find("Block").text if address.find("Block") is not None else ""
            building_unit = address.find("BuildingUnit").text if address.find("BuildingUnit") is not None else ""
            self.add_address_component("Країна", country)
            self.add_address_component("Поштовий індекс", zip_code)
            self.add_address_component("Регіон", region)
            self.add_address_component("Район", district)
            self.add_address_component("Населений пункт", settlement)
            self.add_address_component("Вулиця", street)
            self.add_address_component("Будинок", building)
            self.add_address_component("Корпус", block)
            self.add_address_component("Квартира", building_unit)
    def add_address_component(self, label, value):
        key_item = QStandardItem(label)
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        value_item = QStandardItem(value)
        self.items_model.appendRow([key_item, value_item])



    def add_additional_info(self, element):
        additional_info_block = element.find("AdditionalInfoBlock")
        if additional_info_block is not None:
            additional_infos = additional_info_block.findall("AdditionalInfo")
            for additional_info in additional_infos:
                value = additional_info.text if additional_info is not None else ""
                key_item = QStandardItem("Додаткова інформація")
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(value)
                self.items_model.appendRow([key_item, value_item])