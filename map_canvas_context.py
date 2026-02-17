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
        Централізовано обробляє та викликає дії плагіна з контекстного меню.

        Цей метод працює як диспетчер, який отримує ключ дії (`action_key`)
        та, залежно від його значення, викликає відповідний метод у головному
        класі плагіна, док-віджеті або інших спеціалізованих класах.

        Args:
            action_key (str): Рядковий ідентифікатор дії, що має бути виконана.
                Можливі значення:
                - "new_from_selection": Створити новий XML-файл з виділеного полігону.
                - "add_lands_to_active": Додати угіддя до активного XML.
                - "adjacent": Додати суміжника до активного XML.
                - "lease": Додати оренду до активного XML.
                - "sublease": Додати суборенду до активного XML.
                - "restriction": Додати обмеження до активного XML.
            template_path (str, optional): Шлях до файлу шаблону. Використовується
                тільки разом з `action_key="new_from_selection"` для створення
                XML на основі конкретного шаблону. За замовчуванням `None`.
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
            return

        method_map = {"lease": "add_lease",
                      "sublease": "add_sublease", "restriction": "add_restriction"}
        method_name = method_map.get(action_key)
        if self.plugin.dockwidget and method_name and hasattr(self.plugin.dockwidget, method_name):
            try:
                getattr(self.plugin.dockwidget, method_name)()
            except Exception as e:
                QMessageBox.critical(
                    None, "xml_ua", f"Помилка при виконанні {method_name}: {e}")
        else:
            QMessageBox.information(
                None, "xml_ua", "Функція ще не реалізована у NewXmlCreator.")

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

    def _add_creation_menu(self, menu):
        """Додає до меню пункти для створення нового XML з виділеного полігону."""
        if self._is_single_polygon_selected():
            menu.addSeparator()
            action_new_from_selection = menu.addAction(
                "Створити XML з полігона")
            action_new_from_selection.triggered.connect(
                lambda: self._trigger_plugin_action("new_from_selection"))

            templates_dir = os.path.join(
                os.path.dirname(__file__), 'templates')
            if os.path.exists(templates_dir):
                template_files = [f for f in os.listdir(
                    templates_dir) if f.endswith('.xml') and f != 'template.xml']
                if template_files:
                    templates_menu = menu.addMenu("Створити XML з шаблону")
                    for template_file in sorted(template_files):
                        template_name = os.path.splitext(template_file)[0]
                        template_path = os.path.join(
                            templates_dir, template_file)
                        action = QAction(f"Створити з '{template_name}'", menu)
                        action.triggered.connect(lambda _, t_path=template_path: self._trigger_plugin_action(
                            "new_from_selection", template_path=t_path))
                        templates_menu.addAction(action)

    def _add_geometry_components_menu(self, menu):
        """Додає до меню пункти для додавання геометричних складових до активного XML."""
        if self.plugin.dockwidget and self.plugin.dockwidget.current_xml:
            group_name = self.plugin.dockwidget.current_xml.group_name
            menu_text = f"Додати геометричні складові до «{group_name}»"
            menu.addSeparator()
            xml_ua_menu = menu.addMenu(menu_text)

            actions_config = [
                {"label": "Додати угіддя", "key": "add_lands_to_active",
                    "separator_before": False},
                {"label": "Додати оренду", "key": "lease", "separator_before": True},
                {"label": "Додати суборенду", "key": "sublease",
                    "separator_before": False},
                {"label": "Додати обмеження", "key": "restriction",
                    "separator_before": True},
                {"label": "Додати суміжника", "key": "adjacent",
                    "separator_before": False},
            ]

            for config in actions_config:
                if config["separator_before"]:
                    xml_ua_menu.addSeparator()
                action = QAction(config["label"], self.canvas)
                action.triggered.connect(
                    lambda _, key=config["key"]: self._trigger_plugin_action(key))
                xml_ua_menu.addAction(action)

    def on_context_menu(self, menu, event):
        """
        Формує та відображає кастомне контекстне меню на полотні карти.

        Цей метод викликається щоразу при кліку правою кнопкою миші на карті.
        Він динамічно додає до стандартного меню QGIS додаткові пункти,
        специфічні для плагіна `xml_ua`.

        Args:
            menu (QMenu): Існуюче контекстне меню, до якого додаються нові дії.
            event (QgsMapMouseEvent): Подія миші, що містить інформацію про клік.
        """

        self._add_creation_menu(menu)

        self._add_geometry_components_menu(menu)


def setup_map_canvas_context(iface, plugin):
    """
    Налаштовує та інтегрує кастомне контекстне меню в полотно карти QGIS.

    Ця функція створює обробник контекстного меню (`MapCanvasContextMenu`) та
    підключає його до сигналу `contextMenuAboutToShow` полотна карти. В результаті,
    при кожному кліку правою кнопкою миші на карті, буде викликатися метод
    `on_context_menu`, який динамічно формує та відображає меню плагіна.

    Args:
        iface (QgisInterface): Екземпляр інтерфейсу QGIS, що надає доступ до
                               головних компонентів, зокрема до полотна карти.
        plugin (xml_ua): Екземпляр головного класу плагіна. Потрібен для того,
                         щоб дії з меню могли викликати відповідні методи
                         плагіна (наприклад, додавання суміжника або створення
                         нового XML).

    Returns:
        method or None: Повертає посилання на метод `on_context_menu` створеного
                        обробника, яке необхідне для подальшого коректного
                        від'єднання сигналу при вивантаженні плагіна.
                        Повертає `None`, якщо полотно карти недоступне.
    """
    canvas = iface.mapCanvas()
    if not canvas:
        return None

    context_menu_handler = MapCanvasContextMenu(iface, plugin)
    canvas.contextMenuAboutToShow.connect(context_menu_handler.on_context_menu)
    return context_menu_handler.on_context_menu
