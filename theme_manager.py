

import os
from qgis.core import QgsProject
from collections import namedtuple

Theme = namedtuple("Theme", ["name", "styles"])

EDIT_THEME = Theme(
    name="Редагування XML",
    styles={
        "Ділянка": "parcel.qml",
        "Угіддя": "lands_parcel.qml",
        "Кадастровий квартал": "quarter.qml",
        "Кадастрова зона": "zone.qml",
        "Суміжники": "adjacent.qml",
        "Обмеження": "restriction.qml",
        "Оренда": "lease.qml",
        "Суборенда": "sublease.qml",
        "Полілінії": "lines.qml",
        "Вузли": "points.qml",
    },
)

PLAN_THEME = Theme(
    name="Кадастровий план",
    styles={
        "Ділянка": "parcel_plan.qml",
        "Угіддя": "lands_parcel_plan.qml",
        "Кадастровий квартал": "quarter_plan.qml",
        "Кадастрова зона": "zone_plan.qml",
        "Суміжники": "adjacent_plan.qml",
        "Обмеження": "restrictions_plan.qml",
        "Оренда": "lease_plan.qml",
        "Суборенда": "sublease_plan.qml",
        "Полілінії": "lines_plan.qml",
        "Вузли": "points_plan.qml",
    },
)

THEMES = [EDIT_THEME, PLAN_THEME]


class ThemeManager:
    """Клас для управління темами оформлення шарів."""

    def __init__(self, plugin_dir):
        """
        Ініціалізація менеджера тем.
        :param plugin_dir: Шлях до директорії плагіна.
        """
        self.plugin_dir = plugin_dir
        self.themes = {theme.name: theme for theme in THEMES}

    def get_themes(self):
        """Повертає список назв доступних тем."""
        return list(self.themes.keys())

    def apply_theme(self, theme_name, group_name):
        """
        Застосовує вказану тему до всіх шарів у вказаній групі.

        :param theme_name: Назва теми для застосування.
        :param group_name: Назва групи шарів.
        """
        theme = self.themes.get(theme_name)
        if not theme:
            print(f"Тему '{theme_name}' не знайдено.")
            return

        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup(group_name)
        if not group:
            return

        for child in group.children():
            if hasattr(child, 'layer'):
                layer = child.layer()
                layer_name = layer.name()

                style_filename = theme.styles.get(layer_name)

                if style_filename:
                    style_path = os.path.join(
                        self.plugin_dir, "templates", style_filename)
                    if os.path.exists(style_path):
                        layer.loadNamedStyle(style_path)
                        layer.triggerRepaint()
                    else:
                        print(f"Файл стилю не знайдено: {style_path}")
