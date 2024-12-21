# -*- coding: utf-8 -*-

from . import common

from qgis.PyQt.QtWidgets import QDialog, QInputDialog, QMessageBox, QDateEdit, QVBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem, QMenu
from qgis.PyQt.QtCore import QDate, Qt
import uuid
import os, inspect, sys
import configparser
from datetime import datetime


def input_date(parent=None):
    """
    Ввід дати у форматі YYYY-MM-DD.
    """
    common.log_msg(common.logFile)
    dialog = QDialog(parent)
    dialog.setWindowTitle("Введення дати")

    layout = QVBoxLayout(dialog)
    label = QLabel("Виберіть дату:")
    layout.addWidget(label)

    date_edit = QDateEdit()
    date_edit.setCalendarPopup(True)
    date_edit.setDate(QDate.currentDate())
    layout.addWidget(date_edit)

    button = QPushButton("OK")
    button.clicked.connect(dialog.accept)
    layout.addWidget(button)

    if dialog.exec_() == QDialog.Accepted:
        return date_edit.date().toString("yyyy-MM-dd")
    return None

def regenerate_guid(parent=None):
    """
    Перегенерація нового глобального унікального ідентифікатора (GUID).
    """
    common.log_msg(common.logFile)
    reply = QMessageBox.question(parent, "Перегенерація GUID", "Згенерувати новий GUID?",
                                 QMessageBox.Yes | QMessageBox.No)
    if reply == QMessageBox.Yes:
        return str(uuid.uuid4())
    return None

def select_receiver_name(config, parent=None):
    """
    Вибір зі списку назв обласних філій (з ini-файлу).
    """
    # common.log_msg(common.logFile)
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
        return receiver_name, receiver_keys[index]
    return None, None

def set_software_value(parent=None):
    """
    Встановлення значення 'QGIS xml_ua'.
    """
    common.log_msg(common.logFile)
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
    common.log_msg(common.logFile)
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


def handle_metadata_edit(row_name, config=None, plugin_directory=None, parent=None):
    """
    Визначає, який діалог викликати для конкретного рядка.
    """
    common.log_msg(common.logFile)
    if row_name == "FileDate":
        return input_date(parent)
    elif row_name == "FileGUID":
        return regenerate_guid(parent)
    elif row_name == "ReceiverName":
        return select_receiver_name(config, parent)
    elif row_name == "ReceiverIdentifier":
        _, identifier = select_receiver_name(config, parent)
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
    
    common.log_stack(common.logFile)
    common.log_model(common.logFile, model)
    # common.log_dict(common.logFile, tooltips, msg="tooltips")
    
    if not model:
        common.log_var(common.logFile, "Модель таблиці не встановлена!")
        return

    for row in range(model.rowCount()):  # Перевіряємо всі рядки таблиці
        
        key_item = model.item(row, 0)  # Отримуємо елемент у першій колонці
        
        # common.log_var(common.logFile, f"key_item = {key_item}")
        # common.log_var(common.logFile, f"key_item.text() = {key_item.text()}")

        if key_item and key_item.text() in tooltips:
            
            tooltip_text = tooltips[key_item.text()]
            key_item.setToolTip(tooltip_text)  # Встановлюємо tooltip


# def setup_table_events(table_view, config, plugin_directory):
    # """
        # Налаштовує обробку подій для таблиці.
        # :param table_view: QTableWidget, таблиця.
        # :param config: словники INI-файлу.
        # :param plugin_directory: каталог плагіну.
    # """
    # common.log_msg(common.logFile)
    

    # def handle_double_click(item):
        # """
            # Обробляє подвійний клік для редагування.
        # """
        # common.log_var(common.logFile)
        # item.setFlags(item.flags() | Qt.ItemIsEditable)
        # QMessageBox.warning(None, "Повідомлення", f"Клік")



    # def handle_right_click(table_view, pos):
        # """
        # Обробляє правий клік для виклику handle_metadata_edit.
        # """
        # common.log_stack(common.logFile)
        
        # index = self.tableViewMetadata.indexAt(pos)  # Отримуємо QModelIndex за позицією
        # if not index.isValid():
            # common.log_msg(common.logFile, "Клік поза межами таблиці")
            # return

        # row = index.row()
        # column = index.column()
        # model = self.tableViewMetadata.model()  # Отримуємо модель таблиці
        # value = model.data(index)  # Отримуємо значення з моделі
    
        # common.log_msg(common.logFile, f"Клік на рядку {row}, колонці {column}, значення: {value}")
        # QMessageBox.warning(None, "Повідомлення", f"Клік на рядку {row}, колонці {column}, значення: {value}")



    # table_view.doubleClicked.connect(handle_double_click)
    # # table_view.setContextMenuPolicy(Qt.CustomContextMenu)
    # # table_view.customContextMenuRequested.connect(handle_right_click)
















