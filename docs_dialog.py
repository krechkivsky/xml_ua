# -*- coding: utf-8 -*-
# docs_dialog.py

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

        # Створення області прокрутки
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

        # Кнопки OK та Cancel
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
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
                selected.append((checkbox.property("doc_code"), checkbox.property("doc_name")))
        return selected