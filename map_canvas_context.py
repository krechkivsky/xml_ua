import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox

from qgis.core import QgsProject, QgsWkbTypes
from qgis.utils import iface

from .common import log_msg, logFile

class MapCanvasContextMenu:
    """
    Клас для керування контекстним меню полотна карти.
    """
    def __init__(self, iface, plugin):
        self.iface = iface
        self.plugin = plugin
        self.canvas = self.iface.mapCanvas()

    def _trigger_plugin_action(self, action_key, template_path=None):
        """
        Викликає дію у плагіні:
        """
        from .new_xml import NewXmlCreator
        
        if action_key == "add_lands_to_active":
            if self.plugin.dockwidget:
                self.plugin.dockwidget.add_lands()
            else:
                QMessageBox.warning(None, "xml_ua", "Док-віджет не активний.")
            return
        elif action_key == "adjacent":
            if self.plugin.dockwidget:
                self.plugin.dockwidget.add_adjacent_unit()
            else:
                QMessageBox.warning(None, "xml_ua", "Док-віджет не активний.")
            return
        elif action_key == "new_from_selection":
            creator = NewXmlCreator(self.iface, self.plugin)
            creator.execute(template_path=template_path)
            return # Виходимо після виконання основної дії

        # --- Початок змін: Виклик методів з dockwidget ---
        method_map = {"lease": "add_lease", "sublease": "add_sublease", "restriction": "add_restriction"}
        method_name = method_map.get(action_key)
        if self.plugin.dockwidget and method_name and hasattr(self.plugin.dockwidget, method_name):
            try:
                getattr(self.plugin.dockwidget, method_name)()
            except Exception as e:
                QMessageBox.critical(None, "xml_ua", f"Помилка при виконанні {method_name}: {e}")
        else:
            QMessageBox.information(None, "xml_ua", "Функція ще не реалізована у NewXmlCreator.")

    def _is_single_polygon_selected(self):
        """Перевіряє, чи вибрано один полігональний об'єкт на всіх шарах."""
        selected_features = []
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == layer.VectorLayer:
                selected_features.extend(layer.selectedFeatures())

        if len(selected_features) != 1:
            return False

        feature = selected_features[0]
        geom_type = feature.geometry().wkbType()
        return geom_type in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon)

    def on_context_menu(self, menu, event):
        """Показати розширене меню при правому кліку на полотні карти."""

        # Додаємо пункт для створення нового XML, якщо вибрано один полігон
        if self._is_single_polygon_selected():
            menu.addSeparator()
            action_new_from_selection = menu.addAction("Створити XML з полігона")
            action_new_from_selection.triggered.connect(lambda: self._trigger_plugin_action("new_from_selection"))

            # --- Динамічне додавання шаблонів ---
            templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
            if os.path.exists(templates_dir):
                template_files = [f for f in os.listdir(templates_dir) if f.endswith('.xml') and f != 'template.xml']
                if template_files:
                    templates_menu = menu.addMenu("Створити XML з шаблону")
                    
                    for template_file in sorted(template_files):
                        template_name = os.path.splitext(template_file)[0]
                        template_path = os.path.join(templates_dir, template_file)
                        
                        action = QAction(f"Створити з '{template_name}'", menu)
                        action.triggered.connect(lambda _, t_path=template_path: self._trigger_plugin_action("new_from_selection", template_path=t_path))
                        templates_menu.addAction(action)

        # Додаємо наше меню, тільки якщо є активний XML
        if self.plugin.dockwidget and self.plugin.dockwidget.current_xml:
            # Формуємо назву меню з іменем активної групи
            group_name = self.plugin.dockwidget.current_xml.group_name
            menu_text = f"Додати геометричні складові до «{group_name}»"
            menu.addSeparator()
            xml_ua_menu = menu.addMenu(menu_text)

            a_land = QAction("Додати угіддя", self.canvas)
            a_lease = QAction("Додати оренду", self.canvas)
            a_sublease = QAction("Додати суборенду", self.canvas)
            a_restr = QAction("Додати обмеження", self.canvas)
            a_adj = QAction("Додати суміжника", self.canvas)

            a_land.triggered.connect(lambda: self._trigger_plugin_action("add_lands_to_active"))
            a_lease.triggered.connect(lambda: self._trigger_plugin_action("lease"))
            a_sublease.triggered.connect(lambda: self._trigger_plugin_action("sublease"))
            a_restr.triggered.connect(lambda: self._trigger_plugin_action("restriction"))
            a_adj.triggered.connect(lambda: self._trigger_plugin_action("adjacent"))

            xml_ua_menu.addAction(a_land)
            xml_ua_menu.addSeparator()
            xml_ua_menu.addAction(a_lease)
            xml_ua_menu.addAction(a_sublease)
            xml_ua_menu.addSeparator()
            xml_ua_menu.addAction(a_restr)
            xml_ua_menu.addAction(a_adj)

def setup_map_canvas_context(iface, plugin):
    """
    Налаштовує контекстне меню для полотна карти.
    """
    canvas = iface.mapCanvas()
    if not canvas:
        return None

    context_menu_handler = MapCanvasContextMenu(iface, plugin)
    canvas.contextMenuAboutToShow.connect(context_menu_handler.on_context_menu)
    return context_menu_handler.on_context_menu