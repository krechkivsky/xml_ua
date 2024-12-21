# -*- coding: utf-8 -*-


from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QStyledItemDelegate
from qgis.PyQt.QtWidgets import QLineEdit


class DateMaskDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        # Перевіряємо, чи це правильна комірка (row=0, col=1)
        if index.row() == 0 and index.column() == 1:
            editor = QLineEdit(parent)
            editor.setInputMask("0000-00-00")  # Маска вводу "YYYY-MM-DD"
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if isinstance(editor, QLineEdit):
            editor.setText(index.data(Qt.EditRole))  # Завантаження даних у редактор
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text(), Qt.EditRole)  # Збереження даних із редактора
        else:
            super().setModelData(editor, model, index)


