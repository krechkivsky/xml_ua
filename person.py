
from qgis.PyQt.QtCore import Qt

from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QStandardItemModel

from qgis.PyQt.QtWidgets import QTableView

from .common import log_msg
from .common import log_msg
from .common import logFile

class TableViewNaturalPerson(QTableView):
    """
        Клас таблиці для відображення та роботи з даними фізичної особи.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items_model = QStandardItemModel()
        self.setModel(self.items_model)
        self.items_model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        self.empty_elements = []
    def add_full_name(self, element):
        full_name = element.find("FullName")
        if full_name is not None:
            last_name = full_name.find("LastName").text if full_name.find("LastName") is not None else ""
            first_name = full_name.find("FirstName").text if full_name.find("FirstName") is not None else ""
            middle_name = full_name.find("MiddleName").text if full_name.find("MiddleName") is not None else ""
            value = f"{last_name} {first_name} {middle_name}".strip()
            key_item = QStandardItem("ПІБ")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(value)
            self.items_model.appendRow([key_item, value_item])

    def add_full_name(self, element):
        full_name = element.find("FullName")
        if full_name is not None:
            last_name = full_name.find("LastName").text if full_name.find("LastName") is not None else ""
            first_name = full_name.find("FirstName").text if full_name.find("FirstName") is not None else ""
            middle_name = full_name.find("MiddleName").text if full_name.find("MiddleName") is not None else ""
            key_item = QStandardItem("Прізвище")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(last_name)
            self.items_model.appendRow([key_item, value_item])
            key_item = QStandardItem("Ім'я")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(first_name)
            self.items_model.appendRow([key_item, value_item])
            key_item = QStandardItem("По батькові")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(middle_name)
            self.items_model.appendRow([key_item, value_item])



    def add_tax_number(self, element):
        tax_number = element.find("TaxNumber")
        value = tax_number.text if tax_number is not None else ""
        key_item = QStandardItem("Індивідуальний податковий номер")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        value_item = QStandardItem(value)
        self.items_model.appendRow([key_item, value_item])

    def add_passport(self, element):
        passport = element.find("Passport")
        if passport is not None:
            document_type_element = passport.find("DocumentType")
            document_type_text = document_type_element.text if passport.find("DocumentType") is not None else ""
            path = document_type_element.getroottree().getpath(document_type_element)
            value_item = QStandardItem(document_type_text)
            key_item = QStandardItem("Тип документа")
            key_item.setToolTip("<b>Тип документа</b> <br>")
            value_item.setData(path, Qt.UserRole)
            key_item.setData(path, Qt.UserRole)
            self.items_model.appendRow([key_item, value_item])
            passport_number = passport.find("PassportNumber").text if passport.find("PassportNumber") is not None else ""
            key_item = QStandardItem("Номер паспорта")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(passport_number)
            self.items_model.appendRow([key_item, value_item])
            passport_issued_date = passport.find("PassportIssuedDate").text if passport.find("PassportIssuedDate") is not None else ""
            key_item = QStandardItem("Дата видачі паспорта")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(passport_issued_date)
            self.items_model.appendRow([key_item, value_item])
            issuance_authority = passport.find("IssuanceAuthority").text if passport.find("IssuanceAuthority") is not None else ""
            key_item = QStandardItem("Орган, що видав паспорт")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(issuance_authority)
            self.items_model.appendRow([key_item, value_item])
            passport_series = passport.find("PassportSeries").text if passport.find("PassportSeries") is not None else ""
            key_item = QStandardItem("Серія паспорта")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(passport_series)
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
    def add_citizenship(self, element):
        citizenships = element.findall("Citizenship")
        for citizenship in citizenships:
            value = citizenship.text if citizenship is not None else ""
            key_item = QStandardItem("Громадянство")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(value)
            self.items_model.appendRow([key_item, value_item])
    def add_address(self, element):
        addresses = element.findall("Address")
        for address in addresses:
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

    def add_parcel_part(self, proprietor_info):

        parcel_part = proprietor_info.find(".//ParcelPart")

        if parcel_part is not None:
            percent = parcel_part.find("Percent")
            part = parcel_part.find("Part")
            numerator = part.find("Numerator") if part is not None else None
            denominator = part.find("Denominator") if part is not None else None


            
            if percent is not None:
                value = f"{percent.text}%"
            elif numerator is not None and denominator is not None:
                value = f"{numerator.text}/{denominator.text}"
            else:
                value = ""

            key_item = QStandardItem("Частка у власності")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(value)
            self.items_model.appendRow([key_item, value_item])

    def add_proprietor_code(self, proprietor_info):
        proprietor_code = proprietor_info.find(".//ProprietorCode")
        value = proprietor_code.text if proprietor_code is not None else ""
        key_item = QStandardItem("Шифр рядка власника за формою 6-зем")
        key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        value_item = QStandardItem(value)
        self.items_model.appendRow([key_item, value_item])

    def add_privilege_info(self, proprietor_info):
        privilege = proprietor_info.find(".//Privilege")
        if privilege is not None:
            registration_info = privilege.find("RegistrationInfo")
            if registration_info is not None:
                reg_name = registration_info.find("RegName").text if registration_info.find("RegName") is not None else ""
                registration_date = registration_info.find("RegistrationDate").text if registration_info.find("RegistrationDate") is not None else ""
                
                key_item = QStandardItem("Стаття закону, що передбачає пільгу")
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(reg_name)
                self.items_model.appendRow([key_item, value_item])
                
                key_item = QStandardItem("Дата виникнення права на пільгу")
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(registration_date)
                self.items_model.appendRow([key_item, value_item])

    def add_land_additional_info(self, proprietor_info):
        additional_info_block = proprietor_info.find(".//AdditionalInfoBlock")
        if additional_info_block is not None:
            additional_infos = additional_info_block.findall("AdditionalInfo")
            for additional_info in additional_infos:
                value = additional_info.text if additional_info is not None else ""
                key_item = QStandardItem("Додаткова інформація про земельну ділянку")
                key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                value_item = QStandardItem(value)
                self.items_model.appendRow([key_item, value_item])

    def add_property_acquisition_justification(self, proprietor_info):
        justification = proprietor_info.find(".//PropertyAcquisitionJustification")
        if justification is not None:
            document = justification.find("Document").text if justification.find("Document") is not None else ""
            document_date = justification.find("DocumentDate").text if justification.find("DocumentDate") is not None else ""
            document_number = justification.find("DocumentNumber").text if justification.find("DocumentNumber") is not None else ""
            approval_authority = justification.find("ApprovalAuthority").text if justification.find("ApprovalAuthority") is not None else ""
            key_item = QStandardItem("Назва документа (код)")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(document)
            self.items_model.appendRow([key_item, value_item])
            key_item = QStandardItem("Дата прийняття (укладання) документа")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(document_date)
            self.items_model.appendRow([key_item, value_item])
            key_item = QStandardItem("Номер документа")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(document_number)
            self.items_model.appendRow([key_item, value_item])
            key_item = QStandardItem("Орган, який прийняв рішення")
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            value_item = QStandardItem(approval_authority)
            self.items_model.appendRow([key_item, value_item])


    def populate_natural_person(self, xml_tree, proprietor_info, person):


        self.items_model.removeRows(0, self.items_model.rowCount())

        self.add_parcel_part(proprietor_info)

        self.add_full_name(person)
        self.add_tax_number(person)
        self.add_passport(person)
        self.add_additional_info(person)
        self.add_citizenship(person)
        self.add_address(person)

        self.add_proprietor_code(proprietor_info)

        self.add_privilege_info(proprietor_info)
        self.add_privilege_info(proprietor_info)
        self.add_land_additional_info(proprietor_info)
        self.add_property_acquisition_justification(proprietor_info)



        self.resizeColumnToContents(0)













