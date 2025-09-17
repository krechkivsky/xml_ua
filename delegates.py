# -*- coding: utf-8 -*-
"""
Custom delegates for editing data in tree/table views.
"""
from qgis.PyQt.QtWidgets import QStyledItemDelegate, QComboBox
from qgis.PyQt.QtCore import Qt

class StateActTypeDelegate(QStyledItemDelegate):
    """
    A delegate for editing the 'StateActType' element.
    It presents a QComboBox with predefined state act types.
    It stores the code (1-8) in the model but displays the descriptive text.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state_act_types = {
            "1": "Державний акт на право колективної власності на землю",
            "2": "Державний акт на право приватної власності на землю",
            "3": "Державний акт на право власності на землю",
            "4": "Державний акт на право власності на земельну ділянку",
            "5": "Державний акт на право довічного успадкованого володіння землею",
            "6": "Державний акт на право постійного володіння землею",
            "7": "Державний акт на право постійного користування землею",
            "8": "Державний акт на право постійного користування земельною ділянкою",
        }
        # Створюємо список для QComboBox, зберігаючи порядок
        self.items = list(self.state_act_types.values())

    def _is_target_element(self, index):
        """Checks if the item at the given index is the 'StateActType' element."""
        full_path = index.data(Qt.UserRole)
        return full_path and full_path.endswith("/StateActInfo/StateActType")

    def createEditor(self, parent, option, index):
        """Creates a QComboBox editor if the element is 'StateActType'."""
        if self._is_target_element(index):
            editor = QComboBox(parent)
            editor.addItems(self.items)
            return editor
        # Для всіх інших елементів використовуємо стандартний редактор
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        """Sets the editor's data from the model."""
        if self._is_target_element(index):
            value = index.model().data(index, Qt.EditRole)
            # Знаходимо індекс тексту, що відповідає коду
            try:
                # value - це код (напр. "1"), self.items - список текстів
                # self.items[0] відповідає коду "1"
                idx = int(value) - 1
                if 0 <= idx < len(self.items):
                    editor.setCurrentIndex(idx)
                else:
                    editor.setCurrentIndex(-1) # Якщо код невалідний
            except (ValueError, TypeError):
                editor.setCurrentIndex(-1) # Якщо значення не є числом
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        """Sets the model's data from the editor."""
        if self._is_target_element(index):
            # Зберігаємо код (індекс + 1) як рядок
            value = str(editor.currentIndex() + 1)
            model.setData(index, value, Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def displayText(self, value, locale):
        """
        Displays the descriptive text instead of the code for 'StateActType'.
        
        NOTE: This method is called for ALL items in the column. We cannot check
        the element path here directly. The view decides which delegate to use,
        but the displayText is more general. We will handle display logic
        in the view itself by checking the element type.
        
        For now, this method will be overridden by a check in the view,
        but we can prepare the lookup logic.
        """
        # Цей метод не буде працювати як очікувалось, бо він не має доступу до індексу.
        # Логіку відображення ми реалізуємо через `_create_qt_items_for_element`.
        # Однак, якщо ми встановимо делегат на конкретний item, то це спрацює.
        # Поки що залишимо так, бо основна логіка буде в `createEditor`.
        return super().displayText(value, locale)

