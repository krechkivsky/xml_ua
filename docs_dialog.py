

import re
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QScrollArea, QWidget,
                                 QCheckBox, QDialogButtonBox)
from .common import config_docs


class DocsDialog(QDialog):
    """
    Діалогове вікно для вибору документів зі списку з прапорцями.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вибір документів для додавання")
        self.setMinimumSize(600, 400)

        self.layout = QVBoxLayout(self)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)

        self.checkboxes = []
        self.doc_list = self._load_docs()

        for code, name in self.doc_list.items():
            checkbox = QCheckBox(f"{code} - {name}", self.scroll_widget)
            checkbox.setProperty("doc_code", code)
            checkbox.setProperty("doc_name", name)
            self.scroll_layout.addWidget(checkbox)
            self.checkboxes.append(checkbox)

        self.scroll_area.setWidget(self.scroll_widget)
        self.layout.addWidget(self.scroll_area)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def _load_docs(self):
        """Завантажує список документів з docs_list.ini."""
        docs = {}
        if 'DocsList' in config_docs:
            docs = dict(config_docs['DocsList'])
        return docs

    def get_selected_documents(self):
        """
        Повертає список вибраних документів.

        Returns:
            list: Список кортежів (code, name) для вибраних документів.
        """
        selected = []
        for checkbox in self.checkboxes:
            if checkbox.isChecked():
                selected.append((checkbox.property("doc_code"),
                                checkbox.property("doc_name")))
        return selected


def get_equipment_data_for_doc(tree):
    """
    Збирає та парсить дані про обладнання з AdditionalInfo спеціально для документів.
    """
    equipment_context = {
        'ReceiverModel': '', 'ReceiverSN': '', 'ReceiverCertNo': '', 'ReceiverCertDate': '',
        'TotStatModel': '', 'TotStatSN': '', 'TotStatCertNo': '', 'TotStatCertDate': ''
    }

    additional_info_blocks = tree.findall('.//AdditionalInfoBlock')

    for block in additional_info_blocks:
        for info_element in block.findall('AdditionalInfo'):
            text = info_element.text.strip() if info_element.text else ''

            match = re.match(r"Приймач GPS\s+(.+?)\s+SN\s+(.+)", text)
            if match:
                equipment_context['ReceiverModel'] = match.group(1).strip()
                equipment_context['ReceiverSN'] = match.group(2).strip()
                continue

            match = re.match(
                r"Сертифікат калібрування приймача GPS\s+№\s+(.+?)\s+від\s+(.+)", text)
            if match:
                equipment_context['ReceiverCertNo'] = match.group(1).strip()
                equipment_context['ReceiverCertDate'] = match.group(2).strip()
                continue

    return equipment_context
