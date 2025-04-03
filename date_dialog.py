# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import QDate

from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QDateEdit
from qgis.PyQt.QtWidgets import QPushButton
from qgis.PyQt.QtWidgets import QVBoxLayout
from qgis.PyQt.QtWidgets import QHBoxLayout

from .common import logFile
from .common import log_msg
from .common import log_msg
from .common import connector

class DateInputDialog(QDialog):

    def __init__(self, parent=None, default_date=None):
        super().__init__(parent)
        self.setWindowTitle("Введення дати")

        # Основна вертикальна компоновка
        main_layout = QVBoxLayout(self)

        # Компоновка для дати
        date_layout = QHBoxLayout()
        self.date_edit = QDateEdit(self)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(default_date or QDate.currentDate())
        self.date_edit.setFixedSize(100, 20)  # Розмір віджета дати
        date_layout.addWidget(self.date_edit, alignment=Qt.AlignCenter)
        main_layout.addLayout(date_layout)

        # Компоновка для кнопки
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK", self)
        self.ok_button.setFixedSize(100, 20)  # Розмір кнопки
        #self.ok_button.clicked.connect(self.accept)
        connector.connect(self.ok_button, "clicked", self.accept)
        button_layout.addWidget(self.ok_button, alignment=Qt.AlignCenter)
        main_layout.addLayout(button_layout)

        # Установка мінімального розміру та ширини діалогу
        self.setMinimumWidth(150)
        self.resize(150, 70)  # Початковий розмір діалогу



    def get_date(self):

        answer = self.date_edit.date().toString("yyyy-MM-dd")
        log_msg(logFile, f"answer = {answer}")

        return answer  # Повертає дату у форматі "YYYY-MM-DD"




















