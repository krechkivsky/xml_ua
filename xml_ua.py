
"""
/***************************************************************************
 xml_ua
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
import os.path
import math
import copy

from qgis.core import Qgis
from qgis.core import QgsGeometry
from qgis.core import QgsFeature
from qgis.core import QgsWkbTypes
from qgis.core import QgsMapLayer
from qgis.core import QgsProject
from qgis.core import QgsVectorLayer
from qgis.core import QgsVectorLayerEditUtils
from qgis.core import QgsLayerTreeGroup
from qgis.core import QgsRasterLayer
from qgis.core import QgsLayerTreeLayer

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtCore import QTranslator
from qgis.PyQt.QtCore import QCoreApplication

from qgis.PyQt.QtGui import QIcon

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QMenu
from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtWidgets import QToolButton
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QStyle
from qgis.PyQt.QtWidgets import QFileDialog

from xml.etree import ElementTree as ET

from qgis.core import QgsWkbTypes
from qgis.utils import iface



from .resources import *


from .dockwidget import xml_uaDockWidget


from .common import size
from .common import logFile
from .common import log_msg
from .common import log_calls
from .common import connector
from .common import xml_template
from .common import geometry_to_string



class xml_ua:
    """QGIS Plugin Implementation."""















































    def __init__(self, iface): # after load QGIS, without project 
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """

        self.iface = iface
        self.project = None
        self.xml_layers = None
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(self.plugin_dir,'i18n',f'xml_ua_{locale}.qm')
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&xml_ua')
        self.toolbar = None 
        self.pluginIsActive = False
        self.dockwidget = None
        self.dockwidget_visible = False
        self.new_xml = ""
        self.added_layer = None









        self.existing_layer_ids = set()




        QgsProject.instance().layersAdded.connect(self.on_layers_added)



    def tr(self, message): # after load QGIS, without project
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """


        return QCoreApplication.translate('xml_ua', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        log_msg(logFile)

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToVectorMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action


    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        log_calls(logFile)



        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)






        self.dockwidget = None

        self.pluginIsActive = False


    def unload(self):
        log_calls(logFile, f"actions = {self.actions}")

        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.tr(u'&xml_ua'),
                action)
            self.iface.removeToolBarIcon(action)

        if self.toolbar:
            log_calls(logFile, f"removed toolbar {self.toolbar}")
            self.iface.mainWindow().removeToolBar(self.toolbar)  # Використовуємо mainWindow()
            self.toolbar = None  # Очищаємо посилання на тулбар


    def on_layers_added(self, layers):
        """
        Обробник сигналу про додавання шарів до проекту.  Підключає сигнали лише до нових шарів.
        """
        log_calls(logFile, f"{layers[0].name()}")


        existing_layer_ids = set(QgsProject.instance().mapLayers().keys())

        for layer in layers:

            layer_name = layer.name()
            self.added_layer = layer

            if layer.type() == QgsMapLayer.VectorLayer:


                layer.featureAdded.connect(self.on_feature_added)
                layer.featureDeleted.connect(self.on_feature_removed)
                layer.geometryChanged.connect(self.on_qeometry_changed)








        existing_layer_ids.update(layer.id() for layer in layers)


    def on_feature_added(self, feature_id):
        layer = self.added_layer  
        feature = layer.getFeature(feature_id)
        log_calls(logFile, f"'{layer.name()}'")


    def on_feature_removed(self, feature_id):
        layer = self.added_layer  
        feature = layer.getFeature(feature_id)
        log_calls(logFile, f"'{layer.name()}'")

    
    def on_qeometry_changed(self, feature_id, geometry):
        layer = self.added_layer  
        feature = layer.getFeature(feature_id)
        log_calls(logFile, f"'{layer.name()}' {geometry}")



    def is_layer_in_opened_xmls_group(self, layer):
        """
        Перевіряє, чи належить шар до однієї з груп, що входять до opened_xmls.

        Args:
            layer (QgsVectorLayer): Шар для перевірки.

        Returns:
            bool: True, якщо шар належить до однієї з груп, інакше False.
        """

        layer_name = layer.name()
        log_calls(logFile, f"'{layer_name}'")

        if not self.dockwidget or not hasattr(self.dockwidget, 'opened_xmls'):
            return False

        project = QgsProject.instance()
        root = project.layerTreeRoot()

        for xml_data in self.dockwidget.opened_xmls:
            group_name = xml_data.group_name
            group = root.findGroup(group_name)

            if group:
                for child in group.children():
                    if isinstance(child, QgsLayerTreeLayer):
                        if child.layer() == layer:
                            return True
        return False


    def run(self):
        """
        Executes the plugin's main functionality.
        Called from on_open_tool()

        This method performs the following actions:
        1. Logs the function call.
        2. Checks if a QGIS project is open. If no project is open, logs a message and shows a warning to the user.
        3. If the plugin is not active, activates the plugin and initializes the dock widget if it is not already created.
        4. Adds the dock widget to the QGIS interface and displays it.

        Returns:
            None
        """



        log_calls(logFile)


        if not QgsProject.instance().fileName():
            log_msg(logFile, "Немає відкритого проекту. Плагін не буде запущено.")

            self.iface.messageBar().pushMessage(
                "XML-UA",
                "Плагін вимагає відкритого проекту.",
                level=Qgis.Warning
            )
            return


        existing_dockwidget = self.iface.mainWindow().findChild(xml_uaDockWidget, "")
        if existing_dockwidget:
            self.dockwidget = existing_dockwidget
            log_msg(logFile, "Док віджет вже існує, використовуємо існуючий.")
        else:
            log_msg(logFile, "Док віджет не знайдено. Створюємо новий.")
            if not self.pluginIsActive:
                self.pluginIsActive = True


                if self.dockwidget is None:


                    

                    self.dockwidget = xml_uaDockWidget(parent=self.iface.mainWindow(), iface=self.iface, plugin=self)


                    self.dockwidget.closingPlugin.connect(self.onClosePlugin)
                    self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)
                else:
                    if self.dockwidget.parent is None:
                        self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)




        self.dockwidget.show()    


    def on_save_tool(self):
        log_msg(logFile)
        if self.dockwidget is None:
            log_msg(logFile, "Error: dockwidget is None")
            QMessageBox.warning(self.iface.mainWindow(), "Помилка", "Док віджет не ініціалізовано.")
            return
        self.dockwidget.process_action_save()
        return


    def on_save_as_tool(self):
        log_msg(logFile)
        if self.dockwidget is None:
            log_msg(logFile, "Error: dockwidget is None")
            QMessageBox.warning(self.iface.mainWindow(), "Помилка", "Док віджет не ініціалізовано.")
            return
        self.dockwidget.process_action_save_as()
        return


    def on_check_tool(self):
        log_msg(logFile)
        self.dockwidget.process_action_check()
        return


    def on_open_tool(self): 

        log_calls(logFile)


        
        if not QgsProject.instance().fileName():
            self.iface.messageBar().pushMessage(
                "XML-UA",
                "Плагін вимагає відкритого проекту.",
                level=Qgis.Warning
            )
            return


        self.run()



        self.dockwidget.process_action_open()





    def on_clear_tool(self):
        """
            Clears data from the dock widget and project data.

            This method calls clear_widget_data() and remove_temporary_layers() to 
            remove data from the plugin's dock widget and the QGIS project.
        """

        log_msg(logFile)

        self.clear_widget_data()


        self.remove_temporary_layers()


    def clear_widget_data(self): 

        """Clears data from the dock widget."""
        if self.dockwidget is None:
            return  # Nothing to clear if the dockwidget doesn't exist

        log_msg(logFile)








        tabs_to_keep = ["Структура", "Метадані", "Ділянка"]
        for i in range(self.dockwidget.tabWidget.count() -1, -1, -1): # Зворотній порядок!
            tab_name = self.dockwidget.tabWidget.tabText(i)
            if tab_name not in tabs_to_keep:

                if self.dockwidget.tabWidget.count() > 0:

                    self.dockwidget.tabWidget.removeTab(i)

        self.dockwidget.closed_tabs = []

        self.update_restore_tabs_action() # update menu after removing tab
 

        try:
            tree_model = self.dockwidget.treeViewXML.model
            meta_model = self.dockwidget.tableViewMetadata.model()
            parcel_model = self.dockwidget.tableViewParcel.model()

            for model in [tree_model, meta_model, parcel_model]:
                if model.rowCount() > 0:
                    model.removeRows(0, model.rowCount())
                model.setHorizontalHeaderLabels(["Елемент", "Значення"])

        except AttributeError:
            log_msg(logFile, f"AttributeError: {AttributeError}")
            pass # Handle the case where the dockwidget might not be fully initialized or if some views are missing.

        self.dockwidget.setWindowTitle("XML-файл обміну кадастровою інформацією")
        self.dockwidget.xml_file_name = ""


    def remove_temporary_layers(self):
        """
            Clears all temporary layers ("memory") and 
            empty groups (non-recursively) from the QGIS project.

            Reference: on_clear_tool
        """


        log_calls(logFile, "Очистка даних проекту...")
        project = QgsProject.instance()
        root = project.layerTreeRoot()

        layers_to_remove = []
        for layer_id, layer in project.mapLayers().items():
            if layer.dataProvider().name() == 'memory':
                layers_to_remove.append(layer_id)
        for layer_id in layers_to_remove:
            project.removeMapLayer(layer_id)


        def remove_empty_groups(group):
            """Рекурсивно видаляє порожні групи з дерева шарів."""
            groups_to_remove = []
            for child in group.children():
                if isinstance(child, QgsLayerTreeGroup):
                    remove_empty_groups(child)  # Рекурсивний виклик для дочірніх груп
                    if len(child.children()) == 0:
                        groups_to_remove.append(child)
            for group_to_remove in groups_to_remove:

                group.removeChildNode(group_to_remove)

        remove_empty_groups(root)


    def show_dockwidget(self):
        """
            Shows the dock widget.
            - Creates the dock widget if it doesn't exist.
        """



        if self.dockwidget is None:

            self.dockwidget = xml_uaDockWidget(parent=self.iface.mainWindow(), plugin=self) # Додано parent
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget) # Or your preferred area
        else:
           if self.dockwidget.parent is None:
              self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)
        self.dockwidget.show()


    def initGui(self):




        existing_toolbar = self.iface.mainWindow().findChild(QToolBar, "xml_ua")

        if existing_toolbar:

            self.toolbar = existing_toolbar  # Використовуємо знайдений тулбар
        else:

            self.toolbar = self.iface.addToolBar(u'xml_ua') # Переносимо сюди
            self.toolbar.setObjectName(u'xml_ua') # І сюди




        icon_path = ':/plugins/xml_ua/icon.png'
        self.tools_menu = QMenu(self.iface.mainWindow())

        self.action_new_tool = QAction("Новий", self.iface.mainWindow())

        new_icon = self.iface.mainWindow().style().standardIcon(QStyle.SP_FileIcon)
        self.action_new_tool.setIcon(new_icon)


        self.action_open_tool = QAction("Відкрити", self.iface.mainWindow())


        open_icon = self.iface.mainWindow().style().standardIcon(QStyle.SP_DirOpenIcon)
        self.action_open_tool.setIcon(open_icon)

        self.action_save_tool = QAction("Зберегти", self.iface.mainWindow())

        save_icon = self.iface.mainWindow().style().standardIcon(QStyle.SP_DialogSaveButton)
        self.action_save_tool.setIcon(save_icon)

        self.action_save_as_tool = QAction("Зберегти як...", self.iface.mainWindow())

        save_as_icon = self.iface.mainWindow().style().standardIcon(QStyle.SP_DialogSaveButton)
        self.action_save_as_tool.setIcon(save_as_icon)


        self.action_check_tool = QAction("Перевірити", self.iface.mainWindow())

        check_icon = self.iface.mainWindow().style().standardIcon(QStyle.SP_MessageBoxInformation)
        self.action_check_tool.setIcon(check_icon)
        self.action_clear_data = QAction("Очистити дані", self.iface.mainWindow())
        self.action_restore_tabs = QAction("Відновити закриті вкладки", self.iface.mainWindow())

        self.tools_menu.addActions([self.action_new_tool, self.action_open_tool, self.action_save_tool, self.action_save_as_tool, self.action_check_tool])
        self.tools_menu.addAction(self.action_clear_data)
        self.tools_menu.addAction(self.action_restore_tabs)

        self.tools_button = QToolButton()
        self.tools_button.setIcon(QIcon(icon_path))
        self.tools_button.setMenu(self.tools_menu)
        self.tools_button.setPopupMode(QToolButton.MenuButtonPopup)

        self.action_restore_tabs.setEnabled(False)
        self.dockwidget = None

        connector.connect(self.action_new_tool, "triggered", self.on_new_tool)
        connector.connect(self.action_open_tool, "triggered", self.on_open_tool)
        connector.connect(self.action_save_tool, "triggered", self.on_save_tool)
        connector.connect(self.action_save_as_tool, "triggered", self.on_save_as_tool)
        connector.connect(self.action_check_tool, "triggered", self.on_check_tool)
        connector.connect(self.action_clear_data, "triggered", self.on_clear_tool)
        connector.connect(self.action_restore_tabs, "triggered", self.restore_closed_tabs)
        
        self.tools_button.setObjectName("xml_ua_tools_button")
        self.toolbar.addWidget(self.tools_button)

        connector.connect(self.tools_button, "clicked", self.show_dockwidget)








    def update_restore_tabs_action(self):
        if self.dockwidget:
            closed_tabs_exist = len(self.dockwidget.closed_tabs) > 0
            self.action_restore_tabs.setEnabled(closed_tabs_exist)
        else:
            self.action_restore_tabs.setEnabled(False)


    def restore_closed_tabs(self):
        log_msg(logFile)
        if self.dockwidget:
            self.dockwidget.restore_tabs()
            self.update_restore_tabs_action()


    def on_new_tool(self):

        """Новий файл"""

        log_calls(logFile)



        if not self.dockwidget: self.show_dockwidget()


        selected_feature = self.get_selection()
        if not selected_feature: return
        tree = self.set_intro_metric(selected_feature)


        self.new_xml = self.save_tree_with_intro_metric(tree)
        if not self.new_xml:
            log_calls(logFile, f"Не збережено дерево з ПОПЕРЕДНЬОЮ метрикою")
            return




        self.set_tree_full_metric(tree)
        


        self.dockwidget.process_action_new(tree)


    def set_tree_full_metric(self, tree):




























        log_calls(logFile, f"tree: {size(tree)} B")  


        self.add_land_parcels(tree)

        return tree


    def add_land_parcels(self, tree):













        log_calls(logFile, f"tree: {size(tree)} B")


        parcel_polygon = self.get_parcel_polygon()
        if parcel_polygon is None:
            return tree  # Error already handled in get_parcel_polygon

        remainder_polygon = parcel_polygon


        message_bar = self.iface.messageBar()
        message_bar_item = message_bar.createMessage("Виділіть полігон угіддя")
        message_bar.pushWidget(message_bar_item, Qgis.Info, 0)  # 0 for persistent

        while True:

            selected_polygon = self.wait_for_polygon_selection()
            if selected_polygon is None:
                message_bar.clearWidgets()
                return tree  # User canceled


            if not selected_polygon.within(remainder_polygon):
                QMessageBox.warning(None, "Помилка", "Виділений полігон не є частиною залишку ділянки.")
                continue  # Go back to step 2


            self.add_land_use_to_xml(tree, selected_polygon)
            difference = remainder_polygon.difference(selected_polygon)


            if difference.isEmpty():
                break  # All land use areas are covered
            else:
                remainder_polygon = difference

        message_bar.clearWidgets()
        return tree


    def get_parcel_polygon(self):
        """
        Gets the parcel polygon from the selected feature.
        """
        log_calls(logFile)
        
        selected_feature = self.get_selection()
        if not selected_feature:
            return None  # Error already handled in get_selection

        geometry = selected_feature.geometry()
        if geometry.wkbType() == QgsWkbTypes.Polygon:
            return geometry
        elif geometry.wkbType() == QgsWkbTypes.MultiPolygon:

            return geometry
        else:
            QMessageBox.warning(None, "Помилка", "Неправильний тип геометрії угіддя.")
            return None


    def wait_for_polygon_selection(self):
        """
        Waits for the user to select a polygon on the QGIS canvas.
        """




        selected_feature = self.get_selection()
        if not selected_feature:
            return None
        geometry = selected_feature.geometry()
        if geometry.wkbType() == QgsWkbTypes.Polygon:
            return geometry
        elif geometry.wkbType() == QgsWkbTypes.MultiPolygon:
            return geometry
        else:
            QMessageBox.warning(None, "Помилка", "Неправильний тип геометрії угіддя.")
            return None


    def add_land_use_to_xml(self, tree, land_use_polygon):
        """
        Adds a land use polygon to the XML tree.
        """
        log_calls(logFile)









        parcel_info_element = tree.find(".//CadastralQuarterInfo/Parcels/ParcelInfo")
        if parcel_info_element is None:
            log_msg(logFile, "Не знайдено елемент ParcelInfo.")
            QMessageBox.warning(None, "Помилка", "Не знайдено елемент ParcelInfo.")
            return

        land_use_element = ET.SubElement(parcel_info_element, "LandUse")
        ET.SubElement(land_use_element, "Type").text = "Unknown"  # Replace with actual type





        if land_use_polygon.wkbType() == QgsWkbTypes.Polygon:
            for point in land_use_polygon.asPolygon()[0]:

                pass
        elif land_use_polygon.wkbType() == QgsWkbTypes.MultiPolygon:
            for polygon in land_use_polygon.asMultiPolygon():
                for point in polygon[0]:

                    pass







        source_element = tree.find(
            ".//CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/Externals"
        )
        if source_element is None:
            log_msg(logFile, "Не знайдено елемент ParcelMetricInfo/Externals.")
            QMessageBox.warning(None, "Помилка", "Не знайдено елемент ParcelMetricInfo/Externals.")
            return tree


        parent_element = tree.find(
            ".//CadastralQuarterInfo/Parcels/ParcelInfo"
        )
        if parent_element is None:
            log_msg(logFile, "Не знайдено батьківський елемент для LandsParcel.")
            QMessageBox.warning(None, "Помилка", "Не знайдено батьківський елемент для LandsParcel.")
            return tree


        lands_parcel_element = ET.SubElement(parent_element, "LandsParcel")


        land_parcel_info_element = ET.SubElement(lands_parcel_element, "LandParcelInfo")


        metric_info_element = ET.SubElement(land_parcel_info_element, "MetricInfo")


        externals_element = ET.SubElement(metric_info_element, "Externals")


        for child in source_element:
            externals_element.append(copy.deepcopy(child))

        log_calls(logFile, f"tree: {size(tree)} B")

        return tree


    def get_selection(self):

        """
        Перевіряє, чи вибрано геометричний об'єкт типу полігон або мультиполігон.

        Returns:
            QgsFeature: Вибраний об'єкт, якщо всі перевірки пройдено.
            None: Якщо перевірки не пройдено.
        """

        log_calls(logFile)


        layers = QgsProject.instance().mapLayers().values()


        selected_features = []
        for layer in layers:

            if layer.type() == layer.VectorLayer:  
                selected_features.extend(layer.selectedFeatures())


        if not selected_features:
            QMessageBox.warning(None, 
                "Помилка", 
                "Виділіть полігон меж земельної ділянки.")
            log_calls(logFile, "Виділіть полігон меж земельної ділянки.")
            return None


        if len(selected_features) > 1:
            QMessageBox.warning(None, 
                "Помилка", 
                "Треба вибрати лише один полігон.")
            log_calls(logFile, "Треба вибрати лише один полігон.")
            return None


        selected_feature = selected_features[0]
        geometry_type = selected_feature.geometry().wkbType()
        if geometry_type not in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
            QMessageBox.warning(None, 
                "Помилка", 
                "Межі земельної ділянки повинні бути полігоном або мультиполігоном.")
            log_calls(logFile, f"Межі земельної ділянки повинні бути полігоном або мультиполігоном.")
            return None


        log_calls(logFile, f"Вибраний об'єкт: {size(selected_feature)} B\n" + geometry_to_string(selected_feature.geometry()))
        return selected_feature


    def set_intro_metric(self, selected_feature):
        
        """
        Створює новий XML файл на основі шаблону, додаючи точки та лінії з вибраного об'єкта.
        """














         

        log_calls(logFile, f"Отриманий об'єкт: {size(selected_feature)} B")

        if not selected_feature:
            QMessageBox.warning(None, "Помилка", "Не вибрано жодного об'єкта.")
            return

        if not selected_feature:
            QMessageBox.warning(None, "Помилка", "Не вибрано жодного об'єкта.")
            return


        geometry = selected_feature.geometry()
        geometry_type = geometry.wkbType()

        if geometry_type not in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
            QMessageBox.warning(None, "Помилка", "Геометрія повинна бути полігоном або мультиполігоном.")
            return





        points_list = []
        internals_points_list = []
        if geometry_type == QgsWkbTypes.Polygon:
            points_list.append(geometry.asPolygon()[0])  # Зовнішній контур полігону
        elif geometry_type == QgsWkbTypes.MultiPolygon:
            for polygon in geometry.asMultiPolygon():
                points_list.append(polygon[0])  # Зовнішній контур кожного полігону
                for internal_ring in polygon[1:]:
                    internals_points_list.append(internal_ring)


        if not os.path.exists(xml_template):
            QMessageBox.critical(None, "Помилка", f"Шаблон {xml_template} не знайдено.")
            return


        tree = ET.parse(xml_template)
        root = tree.getroot()



        point_info = root.find(".//InfoPart/MetricInfo/PointInfo")
        if point_info is not None:
            for point in point_info.findall("Point"):
                point_info.remove(point)




        uidp_counter = 1
        for points in points_list:

            points_without_last = points[:-1] if len(points) > 1 else points
            for point in points_without_last:
                point_element = ET.SubElement(point_info, "Point")
                ET.SubElement(point_element, "UIDP").text = str(uidp_counter)
                ET.SubElement(point_element, "PN").text = str(uidp_counter)
                ET.SubElement(point_element, "DeterminationMethod").text = "GPS"

                ET.SubElement(point_element, "X").text = f"{point.y():.3f}"
                ET.SubElement(point_element, "Y").text = f"{point.x():.3f}"
                ET.SubElement(point_element, "H").text = "0.00"
                ET.SubElement(point_element, "MX").text = "0.05"
                ET.SubElement(point_element, "MY").text = "0.05"
                ET.SubElement(point_element, "MH").text = "0.05"
                ET.SubElement(point_element, "Description").text = ""
                uidp_counter += 1
        for points in internals_points_list:

            points_without_last = points[:-1] if len(points) > 1 else points
            for point in points_without_last:
                point_element = ET.SubElement(point_info, "Point")
                ET.SubElement(point_element, "UIDP").text = str(uidp_counter)
                ET.SubElement(point_element, "PN").text = str(uidp_counter)
                ET.SubElement(point_element, "DeterminationMethod").text = "GPS"

                ET.SubElement(point_element, "X").text = f"{point.y():.3f}"
                ET.SubElement(point_element, "Y").text = f"{point.x():.3f}"
                ET.SubElement(point_element, "H").text = "0.00"
                ET.SubElement(point_element, "MX").text = "0.05"
                ET.SubElement(point_element, "MY").text = "0.05"
                ET.SubElement(point_element, "MH").text = "0.05"
                ET.SubElement(point_element, "Description").text = ""
                uidp_counter += 1



        polyline_info = root.find(".//InfoPart/MetricInfo/Polyline")
        if polyline_info is not None:
            for pl in polyline_info.findall("PL"):
                polyline_info.remove(pl)


        ulid_counter = 1
        for points in points_list:


            points_without_last = points[:-1] if len(points) > 1 else points
            for i in range(len(points_without_last)):
                start_point = points_without_last[i]



                end_point = points[(i + 1) % len(points)]  
                length = math.sqrt((end_point.x() - start_point.x())**2 + (end_point.y() - start_point.y())**2)

                pl_element = ET.SubElement(polyline_info, "PL")
                ET.SubElement(pl_element, "ULID").text = str(ulid_counter)
                points_element = ET.SubElement(pl_element, "Points")
                ET.SubElement(points_element, "P").text = str(i + 1)

                ET.SubElement(points_element, "P").text = str((i + 2) if (i + 1) < len(points_without_last) else 1)
                ET.SubElement(pl_element, "Length").text = f"{length:.2f}"
                ulid_counter += 1
        for points in internals_points_list:

            points_without_last = points[:-1] if len(points) > 1 else points
            for i in range(len(points_without_last)):
                start_point = points_without_last[i]



                end_point = points[(i + 1) % len(points)]
                length = math.sqrt((end_point.x() - start_point.x()) ** 2 + (end_point.y() - start_point.y()) ** 2)

                pl_element = ET.SubElement(polyline_info, "PL")
                ET.SubElement(pl_element, "ULID").text = str(ulid_counter)
                points_element = ET.SubElement(pl_element, "Points")
                ET.SubElement(points_element, "P").text = str(i + 1)

                ET.SubElement(points_element, "P").text = str((i + 2) if (i + 1) < len(points_without_last) else 1)
                ET.SubElement(pl_element, "Length").text = f"{length:.2f}"
                ulid_counter += 1















        def add_boundary_lines(points_list, parent_element, is_internal=False):
            """Додає лінії до розділу Boundary/Lines або Internals/Boundary/Lines."""

            log_calls(logFile, f"points_list: {size(points_list)} B")
            
            if is_internal:
                internals_element = parent_element.find("Internals")
                if internals_element is None:
                    internals_element = ET.SubElement(parent_element, "Internals")
                boundary_element = internals_element.find("Boundary")
                if boundary_element is None:
                    boundary_element = ET.SubElement(internals_element, "Boundary")
            else:
                boundary_element = parent_element.find("Boundary")
                if boundary_element is None:
                    boundary_element = ET.SubElement(parent_element, "Boundary")

            lines_element = boundary_element.find("Lines")
            if lines_element is None:
                lines_element = ET.SubElement(boundary_element, "Lines")
            else:

                for line in lines_element.findall("Line"):
                    lines_element.remove(line)

            ulid_counter = 1
            for points in points_list:

                points_without_last = points[:-1] if len(points) > 1 else points
                for i in range(len(points_without_last)):
                    line_element = ET.SubElement(lines_element, "Line")
                    ET.SubElement(line_element, "ULID").text = str(ulid_counter)
                    ulid_counter += 1


            closed_element = boundary_element.find("Closed")
            if closed_element is None:
                ET.SubElement(boundary_element, "Closed").text = "true"
            else:
                closed_element.text = "true"


        cadastral_quarter_info = root.find(".//CadastralQuarterInfo")
        if cadastral_quarter_info is None:
            cadastral_zone_info = root.find(".//CadastralZoneInfo")
            if cadastral_zone_info is None:
                info_part = root.find(".//InfoPart")
                if info_part is None:
                    log_msg(logFile, "Не знайдено елемент InfoPart.")
                    QMessageBox.warning(None, "Помилка", "Не знайдено елемент InfoPart.")
                    return
                cadastral_zone_info = ET.SubElement(info_part, "CadastralZoneInfo")
            cadastral_quarter_info = ET.SubElement(cadastral_zone_info, "CadastralQuarters")
            cadastral_quarter_info = ET.SubElement(cadastral_quarter_info, "CadastralQuarterInfo")

        parcels_element = cadastral_quarter_info.find("Parcels")
        if parcels_element is None:
            parcels_element = ET.SubElement(cadastral_quarter_info, "Parcels")

        parcel_info_element = parcels_element.find("ParcelInfo")
        if parcel_info_element is None:
            parcel_info_element = ET.SubElement(parcels_element, "ParcelInfo")

        parcel_metric_info_element = parcel_info_element.find("ParcelMetricInfo")
        if parcel_metric_info_element is None:
            parcel_metric_info_element = ET.SubElement(parcel_info_element, "ParcelMetricInfo")

        externals_element = parcel_metric_info_element.find("Externals")
        if externals_element is None:
            externals_element = ET.SubElement(parcel_metric_info_element, "Externals")


        add_boundary_lines(points_list, externals_element)

        if internals_points_list:
            add_boundary_lines(internals_points_list, externals_element, is_internal=True)


        log_calls(logFile, f"tree: {size(tree)} B")
        
        return tree


    def save_tree_with_intro_metric(self, tree):




        log_calls(logFile, f"tree before saving: {size(tree)} B")


        save_path, _ = QFileDialog.getSaveFileName(None, "Зберегти XML файл", "", "XML файли (*.xml)")
        if not save_path:

            log_calls(logFile, "Шлях для збереження не вибрано.")
            return None



        tree.write(save_path, encoding="utf-8", xml_declaration=True)

        log_calls(logFile, f"Новий XML файл збережено за адресою: {save_path}")
        self.dockwidget.full_xml_file_name = save_path
        log_calls(logFile, f"tree after saving: {size(tree)} B")

        return save_path

