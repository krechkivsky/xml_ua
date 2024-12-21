# -*- coding: utf-8 -*-
"""
/***************************************************************************
 xml_uaDockWidget
                                 A QGIS plugin
 Processing ukrainian cadastral files.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2024-11-01
        git sha              : $Format:%H$
        copyright            : (C) 2024 by Mike
        email                : michael.krechkivski@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
import sys
import inspect
import configparser

import qgis.utils

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtGui import QStandardItemModel

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import QFile
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtCore import QDate

from qgis.core import QgsProject
from qgis.core import QgsVectorLayer
from qgis.core import QgsFeature
from qgis.core import QgsGeometry
from qgis.core import QgsPointXY
from qgis.core import QgsLineString
from qgis.core import QgsPolygon
from qgis.core import QgsField

from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.PyQt.QtWidgets import QWidget
from qgis.PyQt.QtWidgets import QVBoxLayout
from qgis.PyQt.QtWidgets import QHBoxLayout
from qgis.PyQt.QtWidgets import QMenuBar
from qgis.PyQt.QtWidgets import QMenu
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QPushButton
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QToolButton
from qgis.PyQt.QtWidgets import QStyle
from qgis.PyQt.QtWidgets import QTreeView
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.PyQt.QtWidgets import QLineEdit
from qgis.PyQt.QtWidgets import QTableView
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QDateEdit
from qgis.PyQt.QtWidgets import QAbstractItemView

from qgis.PyQt.QtXml import QDomDocument

from xml.etree import ElementTree as ET
from lxml import etree

from .custom_tree_view import CustomTreeView
from .xml_ua_layers import xmlUaLayers
from .date_dialog import DateInputDialog

from . import common
from . import metadata

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'xml_ua_dockwidget_base.ui'))


def get_xml_file_path():
    
    common.log_msg(common.logFile)
    
    options = QFileDialog.Options()
    options |= QFileDialog.ReadOnly  # Опція лише для читання (необов’язкова)
    
    file_path, _ = QFileDialog.getOpenFileName(None,"Вибір файлу","","Файли XML (*.xml)",options=options)
    common.log_msg(common.logFile, f"Вибраний файл: '{file_path}'" )
    
    return file_path

def save_tree_view_to_xml(tree_view, xmlPath):

    common.log_msg(common.logFile)
    doc = QDomDocument()
    
    model = tree_view.model()
    root_item = model.item(0)
    
    def add_elements_to_dom(parent_dom_element, item):
        common.log_msg(common.logFile)
        for row in range(item.rowCount()):
            child_item = item.child(row, 0)
            value_item = item.child(row, 1)

            element = doc.createElement(child_item.text())
            if value_item and value_item.text():
                element.appendChild(doc.createTextNode(value_item.text()))

            parent_dom_element.appendChild(element)

            add_elements_to_dom(element, child_item)

    # Створюємо кореневий елемент та додаємо до документа
    root_element = doc.createElement(root_item.text())
    doc.appendChild(root_element)
    add_elements_to_dom(root_element, root_item)

    # Збереження документа у файл
    with open(xmlPath, 'w', encoding='utf-8') as file:
        file.write('<?xml version="1.0" encoding="utf-8"?>\n  ' + doc.toString(2))  # 4 — це відступ для читабельності

    common.log_msg(common.logFile, f"Зміни збережено у {xmlPath}")

def get_points_xml(xmlPath):
    
    global pointsData
    global XYs
    
    common.log_msg(common.logFile)
    tree = ET.parse(xmlPath)
    root = tree.getroot()
    pointsData = []
    XYs = []
    
    for point in root.findall(".//PointInfo/Point"):
        uid = point.find("UIDP").text if point.find("UIDP") is not None else None
        pn = point.find("PN").text if point.find("PN") is not None else None
        x = point.find("X").text if point.find("X") is not None else None
        y = point.find("Y").text if point.find("Y") is not None else None
        h = point.find("H").text if point.find("H") is not None else None
        mx = point.find("MX").text if point.find("MX") is not None else None
        my = point.find("MY").text if point.find("MY") is not None else None
        mh = point.find("MH").text if point.find("MH") is not None else None
        description = point.find("Description").text if point.find("Description") is not None else None

        pointsData.append({
            "uid": uid,
            "pn": pn,
            "x": x,
            "y": y,
            "h": h,
            "mx": mx,
            "my": my,
            "mh": mh,
            "description": description
        })
        
        XYs.append({
            "uid": uid,
            "x": x,
            "y": y,
        })
    
    
    return

def layer_in_project(layer_name):


    common.log_msg(common.logFile)
    layers = QgsProject.instance().mapLayers().values()
    
    for layer in layers:
        if layer.name() == layer_name:
            return layer
    return None

def add_points_to_qgis(xmlPath):
    global pointsData
    global treeViewKadNum
    
    common.log_msg(common.logFile, " treeViewKadNum = " + treeViewKadNum)
    layer_name = treeViewKadNum + "_точки"
    common.log_msg(common.logFile, " layer_name = " + layer_name)
    layer = layer_in_project(layer_name)
    common.log_msg(common.logFile, "crs=" + crsEpsg)
   
    if not layer: layer = QgsVectorLayer("Point?crs=" + crsEpsg, layer_name, "memory")
    
    provider = layer.dataProvider()
    
    provider.addAttributes([
    QgsField("UIDP", QVariant.String),
    QgsField("PN", QVariant.String),
    #QgsField("X", QVariant.String),
    #QgsField("Y", QVariant.String),
    QgsField("H", QVariant.String),
    QgsField("MX", QVariant.String),
    QgsField("MY", QVariant.String),
    QgsField("MH", QVariant.String),
    QgsField("Description", QVariant.String)])
    layer.updateFields()
    
    for point_data in pointsData:
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(point_data["y"]), float(point_data["x"]))))
        #common.log_msg(common.logFile, " point_data['y'] = " + point_data["y"])
            
        feature.setAttributes([
            point_data["uid"],
            point_data["pn"],
            #point_data["x"],
            #point_data["y"],
            point_data["h"],
            point_data["mx"],
            point_data["my"],
            point_data["mh"],
            point_data["description"]])
        provider.addFeature(feature)

    #common.log_msg(common.logFile, " pointsData = " + str(pointsData))

    # Додавання шару до проекту QGIS
    QgsProject.instance().addMapLayer(layer)

    
    return


class xml_uaDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self):
        """Конструктор."""
        common.log_msg(common.logFile)
        super().__init__()
        self.setupUi(self)
        self.xsd_path = common.xsd_path
        
        # Ініціалізація вкладки дерева
        # Перевіряємо, чи існує treeViewXML типу QTreeView (створений в UI файлі)
        old_tree_view = self.findChild(QTreeView, "treeViewXML")
        if old_tree_view:
            # Видаляємо старий-UI віджет із менеджера компоновки
            layout = self.tabXML.layout()
            if layout:
                layout.removeWidget(old_tree_view)
            # Від'єднати й знищити
            old_tree_view.setParent(None)
            old_tree_view.deleteLater()

        # Додаємо новий віджет типу CustomTreeView
        self.treeViewXML = CustomTreeView(self.tabXML, table_view_metadata=self.tableViewMetadata)
        self.treeViewXML.setObjectName("treeViewXML")  # Залишаємо те саме ім'я
        self.tabXML.layout().addWidget(self.treeViewXML)  # Додаємо до layout
        
        self.treeViewXML.setSelectionMode(QAbstractItemView.NoSelection)


        # Контекстне меню дерева XML
        self.treeViewXML.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeViewXML.customContextMenuRequested.connect(self.treeViewXML.show_context_menu)
        self.treeViewXML.dataChangedSignal.connect(self.on_tree_view_data_changed)

        # Ініціалізація таблиці Метаданих
        self.tableViewMetadata = self.findChild(QTableView, "tableViewMetadata")
        
        self.tableViewMetadata.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tableViewMetadata.customContextMenuRequested.connect(self.handle_right_click)

        # Встановлення обробника подвійного кліку
        self.tableViewMetadata.doubleClicked.connect(self.handle_double_click)
        # # Щоб подвійний клік працював коректно, переконайтесь, що режим виділення дозволяє виділення комірок
        # self.tableViewMetadata.setSelectionMode(QAbstractItemView.SingleSelection) # Або ExtendedSelection, якщо потрібно кілька виділень
        # self.tableViewMetadata.setSelectionBehavior(QAbstractItemView.SelectItems) # Важливо для виділення комірок


        self.tooltips = dict(common.config['metaDataTooltips'])
        # common.log_dict(common.logFile, self.tooltips, msg="tooltips")

        # Підключення подій для таблиці
        # plugin_directory = os.path.dirname(__file__)
        # metadata.setup_table_events(self.tableViewMetadata, common.config, plugin_directory)
        
        # Виклик функцій для додавання меню
        self.add_menu_buttons()

    def handle_right_click(self, position):
        """
        Обробляє правий клік для виклику handle_metadata_edit.
        """
        common.log_stack(common.logFile)
        
        index = self.tableViewMetadata.indexAt(position)  # Отримуємо QModelIndex за позицією
        if not index.isValid():
            common.log_msg(common.logFile, "Клік поза межами таблиці")
            return

        # Перевірка, чи комірка є row=0, col=1
        if index.row() == 0 and index.column() == 1:
            # Створення контекстного меню
            menu = QMenu()
            self.open_date_dialog(index)

        # common.log_msg(common.logFile, f"Правий клік на рядку {index.row()}, колонці {index.column()}")

    def open_date_dialog(self, index):
        # Створення діалогу вводу дати
        current_value = index.data(Qt.EditRole)
        default_date = QDate.fromString(current_value, "yyyy-MM-dd") if current_value else QDate.currentDate()
        dialog = DateInputDialog(default_date=default_date)

        if dialog.exec_() == QDialog.Accepted:
            # Отримання дати з діалогу та оновлення моделі
            new_date = dialog.get_date()
            self.tableViewMetadata.model().setData(index, new_date, Qt.EditRole)

    def handle_double_click(self, index: QModelIndex):
        """
        Обробляє  клік для виклику handle_metadata_edit.
        """
        common.log_stack(common.logFile)
        
        if not index.isValid():
            common.log_msg(common.logFile, "Клік поза межами таблиці")
            return

        row = index.row()
        column = index.column()
        model = self.tableViewMetadata.model()  # Отримуємо модель таблиці
        value = model.data(index)  # Отримуємо значення з моделі
    
        common.log_msg(common.logFile, f"Подвійний клік на рядку {row}, колонці {column}, значення: {value}")
        QMessageBox.warning(None, "Повідомлення", f"Подвійний клік на рядку {row}, колонці {column}, значення: {value}")

    def load_data(self, xml_path, xsd_path):
        """
            Викликає функції завантаження: 
                -  XML у віджет дерева 
                -  метаданих у віджет таблиці (тимчасово:)
        """

        common.log_msg(common.logFile, "Виклик функцій заповнення дерева та таблиці")

        """ заповнення дерева """
        self.treeViewXML.load_xml_to_tree_view(xml_path, xsd_path)

        """ заповнення таблиці Метадані """
        # викликаємо метод об'єкта treeViewXML класу CustomTreeView
        # у майбутньому треба зробити окремий клас CustomTableView
        # self.treeViewXML.populate_tableview_metadata(self.treeViewXML.xmlTree, self.treeViewXML.tableViewMetadata)
        self.treeViewXML.populate_tableview_metadata(self.treeViewXML.xmlTree, self.treeViewXML.tableViewMetadata, self.tooltips)

    def on_tree_view_data_changed(self, path, value):
        """
        Оновлення tableViewMetadata при зміні даних у treeViewXML.
        """
        common.log_msg(common.logFile)
        metadata_model = self.tableViewMetadata.model()
        if not metadata_model:
            return

        for row in range(metadata_model.rowCount()):
            key_item = metadata_model.item(row, 0)
            if key_item and key_item.text() == path:
                value_item = metadata_model.item(row, 1)
                value_item.setText(value)
                break

    def closeEvent(self, event):
        # Логування при закритті плагіну
        common.log_msg(common.logFile)
        self.closingPlugin.emit()
        event.accept()

    def add_menu_buttons(self):
        """
        Додає дві кнопки з випадаючими меню в основний інтерфейс QDockWidget, 
        включаючи стандартні іконки Qt і користувацьку іконку для дії перевірки синтаксису.
        """
        common.log_msg(common.logFile)
        # Створюємо перше меню з іконками
        # logging(common.logFile)
        menu1 = QMenu("Меню 1", self)
    
        # Стандартні дії з іконками
        action_new = QAction(self.style().standardIcon(QStyle.SP_FileIcon), "Новий", self)
        action_open = QAction(self.style().standardIcon(QStyle.SP_DirOpenIcon), "Відкрити", self)
        action_save = QAction(self.style().standardIcon(QStyle.SP_DialogSaveButton), "Зберегти", self)
        action_save_as = QAction(self.style().standardIcon(QStyle.SP_DialogSaveButton), "Зберегти як...", self)
    
        # Додавання користувацької іконки для дії перевірки синтаксису
        custom_icon_path = os.path.dirname(__file__) + "/images/check32x32.png"  # Задайте шлях до іконки
        action_check = QAction(QIcon(custom_icon_path), "Перевірити", self)
    
        # Додаємо дії до меню
        menu1.addAction(action_new)
        menu1.addAction(action_open)
        menu1.addAction(action_save)
        menu1.addAction(action_save_as)
    
        # Додаємо горизонтальний розділювач
        menu1.addSeparator()
    
        # Додаємо дію перевірки синтаксису з користувацькою іконкою
        menu1.addAction(action_check)
    
        # Створюємо першу кнопку меню
        menu_button1 = QToolButton(self)
        menu_button1.setText("Файл")  # Іконка або текст для кнопки
        menu_button1.setMenu(menu1)
        menu_button1.setPopupMode(QToolButton.InstantPopup)
        menu_button1.setFixedSize(44, 24)  # Обмеження розміру кнопки
    
        # Створюємо друге меню для довідкових дій
        menu2 = QMenu("Меню 2", self)
        action_help = QAction(self.style().standardIcon(QStyle.SP_MessageBoxQuestion), "Допомога", self)
        action_about = QAction(self.style().standardIcon(QStyle.SP_MessageBoxInformation), "Про програму", self)
    
        # Додаємо дії до другого меню
        menu2.addAction(action_help)
        menu2.addAction(action_about)
    
        # Створюємо другу кнопку меню
        menu_button2 = QToolButton(self)
        menu_button2.setText("Допомога")  # Іконка або текст для кнопки
        menu_button2.setMenu(menu2)
        menu_button2.setPopupMode(QToolButton.InstantPopup)
        menu_button2.setFixedSize(64, 24)  # Обмеження розміру кнопки
    
        # Створюємо контейнерний віджет для кнопок і горизонтальний макет
        button_container = QWidget(self)
        button_container.setMinimumWidth(150)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(menu_button1)
        button_layout.addWidget(menu_button2)
        button_layout.addStretch()  # Додаємо розтягнення для вирівнювання кнопок ліворуч
    
        # Основний макет для QDockWidget
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(button_container)
        main_layout.addStretch()  # Відступ знизу, щоб кнопки залишались зверху
        self.setLayout(main_layout)
    
        # Підключення обробників дій
        action_new.triggered.connect(lambda: print("Створено новий документ"))
        action_open.triggered.connect(self.process_action_open)
        action_save.triggered.connect(self.process_action_save)
        action_save_as.triggered.connect(self.process_action_save_as)
        action_check.triggered.connect(lambda: print("Перевірка синтаксису"))
        action_help.triggered.connect(lambda: print("Допомога"))
        action_about.triggered.connect(lambda: print("Про програму"))

    def process_action_open(self):
        
        """Обробка події відкриття файлу XML."""
        common.log_msg(common.logFile)
        xml_path, _ = QFileDialog.getOpenFileName(self, "Відкрити XML файл", "", "XML файли (*.xml)")
        # logging(common.logFile, f"xml_path = {xml_path}")
        if not xml_path:
            QMessageBox.warning(self, "Помилка", "Файл не вибрано.")
            return
    
        self.load_data(xml_path, self.xsd_path)
        
        
        self.treeViewXML.expand_initial_elements()
        self.treeViewXML.set_column_width(0, 75)

        projectLayers = xmlUaLayers(xml_path)

        return

    def process_action_save(self):
        global treeViewXml
        global treeViewKadNum

        common.log_msg(common.logFile)
        folder_path = QFileDialog.getExistingDirectory(None, "Виберіть папку для збереження")
        
        if folder_path:
            # Додаємо ім'я файлу до обраного шляху
            full_path = f"{folder_path}/{treeViewKadNum}.xml"
            QMessageBox.information(None, "Шлях для збереження", f"Файл буде збережено як: {full_path}")
            save_tree_view_to_xml(treeViewXml, full_path)
            return 
        else:
            # Якщо користувач скасував вибір
            QMessageBox.warning(None, "Відміна", "Папка не вибрана.")
            return None        

    def process_action_save_as(self):
        global treeViewXml
        global xmlPath

        common.log_msg(common.logFile)
        folder_path = QFileDialog.getExistingDirectory(self, "Виберіть папку для збереження")
        if not folder_path:
            QMessageBox.warning(self, "Помилка", "Папку не вибрано.")
            return
    
        save_path = os.path.join(folder_path, "збережений_файл.xml")
        self.treeViewXML.save_tree_view_to_xml(save_path)
        QMessageBox.information(self, "Успіх", f"Файл збережено: {save_path}")
