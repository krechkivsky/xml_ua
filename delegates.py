

"""
Custom delegates for editing data in tree/table views.
"""
import re
from lxml import etree
from .common import config, config_docs
from qgis.PyQt.QtWidgets import (QStyledItemDelegate, QComboBox, QDialog,
                                 QInputDialog, QMessageBox, QApplication)
from qgis.PyQt.QtCore import Qt, pyqtSignal


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

        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        """Sets the editor's data from the model."""
        if self._is_target_element(index):
            value = index.model().data(index, Qt.EditRole)

            try:

                idx = int(value) - 1
                if 0 <= idx < len(self.items):
                    editor.setCurrentIndex(idx)
                else:
                    editor.setCurrentIndex(-1)  # Якщо код невалідний
            except (ValueError, TypeError):
                editor.setCurrentIndex(-1)  # Якщо значення не є числом
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        """Sets the model's data from the editor."""
        if self._is_target_element(index):

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

        return super().displayText(value, locale)


class DocumentationTypeDelegate(QStyledItemDelegate):
    """
    Делегат для редагування елемента 'DocumentationType'.
    Відображає QComboBox з типами документації.
    Зберігає код, але показує назву.
    """

    documentationTypeChanged = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc_types = self._load_doc_types()

        self.items = list(self.doc_types.values())

        self.reverse_doc_types = {v: k for k, v in self.doc_types.items()}

    def _load_doc_types(self):
        """Завантажує типи документації з файлу конфігурації."""
        if 'DocumentationTypes' in config_docs:

            return dict(sorted(config_docs['DocumentationTypes'].items()))
        return {}

    def _is_target_element(self, index):
        """Перевіряє, чи є елемент 'DocumentationType'."""
        full_path = index.data(Qt.UserRole)
        return full_path and full_path.endswith("/TechnicalDocumentationInfo/DocumentationType")

    def createEditor(self, parent, option, index):
        """Створює QComboBox редактор, якщо елемент 'DocumentationType'."""
        if self._is_target_element(index):
            editor = QComboBox(parent)
            editor.addItems(self.items)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        """Встановлює дані редактора з моделі."""
        if self._is_target_element(index):
            code = index.model().data(index, Qt.EditRole)
            text_value = self.doc_types.get(code, "")
            idx = editor.findText(text_value)
            if idx != -1:
                editor.setCurrentIndex(idx)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        """Встановлює дані моделі з редактора."""
        if self._is_target_element(index):

            text_value = editor.currentText()
            code = self.reverse_doc_types.get(text_value)
            if code:


                model.setData(index, code, Qt.EditRole)

                self.documentationTypeChanged.emit(code, index)
        else:
            super().setModelData(editor, model, index)

    def update_document_list(self, doc_type_code, index):
        """Оновлює елементи DocumentList на основі вибраного DocumentationType."""
        tree_view = self.parent()
        if not tree_view:
            return

        section_map = {
            "006": "DocsListBoundaries",
            "008": "DocsListDivide",
            "009": "DocsListServitute",
        }
        section_name = section_map.get(doc_type_code, "DocsListProject")

        if section_name in config_docs:
            new_doc_codes = list(config_docs[section_name].keys())
        else:

            return

        model = tree_view.model
        doc_type_item = model.itemFromIndex(index)
        tech_doc_info_item = doc_type_item.parent()
        if not tech_doc_info_item or not tech_doc_info_item.data(Qt.UserRole).endswith("TechnicalDocumentationInfo"):
            return

        tech_doc_info_path = tech_doc_info_item.data(Qt.UserRole)
        tech_doc_info_xml_element = tree_view._find_xml_element_by_path(
            tech_doc_info_path)
        if tech_doc_info_xml_element is None:
            return

        for xml_child in tech_doc_info_xml_element.findall("DocumentList"):
            tech_doc_info_xml_element.remove(xml_child)

        for doc_code in new_doc_codes:

            new_xml_elem = etree.SubElement(
                tech_doc_info_xml_element, "DocumentList")
            new_xml_elem.text = doc_code

        tree_view.rebuild_tree_view()

        tree_view.mark_as_changed()

        QApplication.processEvents()

    def displayText(self, value, locale):
        """Відображає назву типу документації замість коду."""
        return self.doc_types.get(str(value), str(value))


class CategoryDelegate(QStyledItemDelegate):
    """
    Делегат для редагування елемента 'Category'.
    Відображає QComboBox з категоріями земель.
    Зберігає код, але показує назву.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.category_types = self._load_categories()

        self.items = list(self.category_types.values())

        self.reverse_category_types = {
            v: k for k, v in self.category_types.items()}

    def _load_categories(self):
        """Завантажує категорії з файлу конфігурації."""
        if 'LandCategories' in config:
            return dict(config['LandCategories'])
        return {}

    def _is_target_element(self, index):
        """Перевіряє, чи є елемент 'Category'."""
        full_path = index.data(Qt.UserRole)
        return full_path and full_path.endswith("/CategoryPurposeInfo/Category")

    def createEditor(self, parent, option, index):
        """Створює QComboBox редактор, якщо елемент 'Category'."""
        if self._is_target_element(index):
            editor = QComboBox(parent)
            editor.addItems(self.items)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        """Встановлює дані редактора з моделі."""
        if self._is_target_element(index):
            code = index.model().data(index, Qt.EditRole)
            text_value = self.category_types.get(code, "")
            idx = editor.findText(text_value)
            if idx != -1:
                editor.setCurrentIndex(idx)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        """Встановлює дані моделі з редактора."""
        if self._is_target_element(index):

            selected_index = editor.currentIndex()
            if selected_index != -1:
                code = list(self.category_types.keys())[selected_index]
                model.setData(index, code, Qt.EditRole)

        else:
            super().setModelData(editor, model, index)

    def displayText(self, value, locale):
        """Відображає назву категорії замість коду."""
        return self.category_types.get(str(value), str(value))


class PurposeDelegate(QStyledItemDelegate):
    """
    Делегат для редагування елемента 'Purpose'.
    Реалізує двокроковий вибір: спочатку розділ, потім підрозділ.
    Зберігає код підрозділу, але показує його назву.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chapters = self._load_data('LandPurposeChapters')
        self.subchapters = self._load_data('LandPurposeSubchapters')

        self.all_purposes = {**self.chapters, **self.subchapters}

    def _load_data(self, section):
        """Завантажує дані з вказаної секції конфігураційного файлу."""
        if section in config:

            return dict(sorted(config[section].items()))
        return {}

    def _is_target_element(self, index):
        """Перевіряє, чи є елемент 'Purpose'."""
        full_path = index.data(Qt.UserRole)
        return full_path and full_path.endswith("/CategoryPurposeInfo/Purpose")

    def createEditor(self, parent, option, index):
        """
        Запускає діалоги вибору замість створення вбудованого редактора.
        """
        if not self._is_target_element(index):
            return super().createEditor(parent, option, index)

        chapter_items = [f"{code} - {name}" for code,
                         name in self.chapters.items()]
        chapter_selection, ok1 = QInputDialog.getItem(parent, "Вибір цільового призначення (Крок 1/2)",
                                                      "Виберіть розділ:", chapter_items, 0, False)

        if not ok1 or not chapter_selection:
            return None  # Користувач скасував вибір

        selected_chapter_code = chapter_selection.split(' - ')[0]

        subchapter_items = {
            code: name for code, name in self.subchapters.items()
            if code.startswith(selected_chapter_code + '.')
        }

        if not subchapter_items:
            QMessageBox.information(
                parent, "Інформація", "Для вибраного розділу немає підрозділів.")
            return None

        subchapter_display_items = [
            f"{code} - {name}" for code, name in subchapter_items.items()]
        subchapter_selection, ok2 = QInputDialog.getItem(parent, "Вибір цільового призначення (Крок 2/2)",
                                                         "Виберіть підрозділ:", subchapter_display_items, 0, False)

        if not ok2 or not subchapter_selection:
            return None  # Користувач скасував вибір

        selected_subchapter_code = subchapter_selection.split(' - ')[0]

        self.selected_code = selected_subchapter_code

        return QDialog(parent)

    def setModelData(self, editor, model, index):
        """Встановлює дані моделі з вибраного значення."""
        if self._is_target_element(index) and hasattr(self, 'selected_code'):
            model.setData(index, self.selected_code, Qt.EditRole)
            del self.selected_code  # Очищуємо тимчасове значення
        else:
            super().setModelData(editor, model, index)

    def setEditorData(self, editor, index):
        """
        Цей метод не потрібен, оскільки ми не встановлюємо початкове значення
        в діалозі, а завжди починаємо вибір заново.
        """
        pass

    def displayText(self, value, locale):
        """Відображає назву цільового призначення замість коду."""
        return self.all_purposes.get(str(value), str(value))


class OwnershipCodeDelegate(QStyledItemDelegate):
    """
    Делегат для редагування застарілого елемента 'OwnershipInfo/Code'.
    Відображає QComboBox з формами власності.
    Зберігає код, але показує назву.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ownership_forms = self._load_forms()

        self.items = list(self.ownership_forms.values())

        self.reverse_ownership_forms = {
            v: k for k, v in self.ownership_forms.items()}

    def _load_forms(self):
        """Завантажує форми власності з файлу конфігурації."""
        if 'OwnershipForms' in config:
            return dict(config['OwnershipForms'])
        return {}

    def _is_target_element(self, index):
        """Перевіряє, чи є елемент 'OwnershipInfo/Code'."""
        full_path = index.data(Qt.UserRole)
        return full_path and full_path.endswith("/OwnershipInfo/Code")

    def createEditor(self, parent, option, index):
        """Створює QComboBox редактор."""
        if self._is_target_element(index):
            editor = QComboBox(parent)
            editor.addItems(self.items)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        """Встановлює дані редактора з моделі."""
        if self._is_target_element(index):
            code = index.model().data(index, Qt.EditRole)
            text_value = self.ownership_forms.get(code, "")
            idx = editor.findText(text_value)
            if idx != -1:
                editor.setCurrentIndex(idx)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        """Встановлює дані моделі з редактора."""
        if self._is_target_element(index):

            selected_index = editor.currentIndex()
            if selected_index != -1:
                code = list(self.ownership_forms.keys())[selected_index]
                model.setData(index, code, Qt.EditRole)

        else:
            super().setModelData(editor, model, index)

    def displayText(self, value, locale):
        """Відображає назву форми власності замість коду."""
        return self.ownership_forms.get(str(value), str(value))


class LandCodeDelegate(QStyledItemDelegate):
    """
    Делегат для редагування елемента 'LandCode' в угіддях.
    Відображає QComboBox з кодами угідь.
    Зберігає код, але показує назву.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.land_codes = self._load_land_codes()

        self.items = [f"{code} - {name}" for code,
                      name in self.land_codes.items()]

        self.reverse_land_codes = {
            f"{code} - {name}": code for code, name in self.land_codes.items()}

    def _load_land_codes(self):
        """Завантажує коди угідь з файлу конфігурації."""
        if 'LandCodes' in config:
            return dict(sorted(config['LandCodes'].items()))
        if 'LandsCode' in config:
            return dict(sorted(config['LandsCode'].items()))
        return {}

    def _is_target_element(self, index):
        """Перевіряє, чи є елемент 'LandCode'."""
        full_path = index.data(Qt.UserRole)
        return full_path and full_path.endswith("/LandParcelInfo/LandCode")

    def createEditor(self, parent, option, index):
        """Створює QComboBox редактор, якщо елемент 'LandCode'."""
        if self._is_target_element(index):
            editor = QComboBox(parent)
            editor.addItems(self.items)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        """Встановлює дані редактора з моделі."""
        if self._is_target_element(index):
            code = index.model().data(index, Qt.EditRole)
            text_value = self.land_codes.get(code, "")
            display_text = f"{code} - {text_value}"
            idx = editor.findText(display_text)
            if idx != -1:
                editor.setCurrentIndex(idx)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        """Встановлює дані моделі з редактора."""
        if self._is_target_element(index):
            text_value = editor.currentText()
            code = self.reverse_land_codes.get(text_value)
            if code:
                model.setData(index, code, Qt.EditRole)
        else:
            super().setModelData(editor, model, index)


class DocumentCodeDelegate(QStyledItemDelegate):
    """
    Делегат для редагування та відображення кодів документів.
    Відображає назву документа замість коду, а редагування
    відбувається через випадаючий список.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree_view = parent
        self.doc_list = self._load_docs()
        self.reverse_doc_list = {v: k for k, v in self.doc_list.items()}

    def _load_docs(self):
        """Завантажує списки документів з config_docs, що в common.py."""
        if 'DocsList' in config_docs:
            return dict(config_docs['DocsList'])
        else:

            return {}

    def createEditor(self, parent, option, index):
        """Створює QComboBox з випадаючим списком документів."""
        if self._is_target_element(index):
            editor = QComboBox(parent)
            for code, name in self.doc_list.items():

                editor.addItem(f"{code} - {name}", code)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        """Встановлює поточне значення в редакторі."""
        if self._is_target_element(index):
            value = index.model().data(index, Qt.EditRole)
            idx = editor.findData(value)
            if idx != -1:
                editor.setCurrentIndex(idx)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        """Зберігає вибраний код документа в модель."""
        if self._is_target_element(index):
            code = editor.currentData()  # Отримуємо код, збережений в userData
            model.setData(index, code, Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def displayText(self, value, locale):
        """Відображає назву документа замість коду."""

        return self.doc_list.get(str(value), str(value))

    def _is_target_element(self, index):
        """Перевіряє, чи є елемент кодом документа."""
        item = self.tree_view.model.itemFromIndex(index)
        if not item or index.column() != 1:
            return False

        parent_item = item.parent()
        if not parent_item:
            return False

        try:
            full_path = parent_item.child(item.row(), 0).data(Qt.UserRole) or ""
            schema_path = re.sub(r"\\[\\d+\\]", "", str(full_path))
            return schema_path.endswith("/DocumentList")
        except Exception:
            return False


class ClosedDelegate(QStyledItemDelegate):
    """
    Делегат для редагування елемента 'Closed'.
    Відображає QComboBox з варіантами "Так" / "Ні".
    Зберігає 'true'/'false', але показує "Так"/"Ні".
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.closed_options = {"true": "Так", "false": "Ні"}
        self.items = list(self.closed_options.values())
        self.reverse_closed_options = {
            v: k for k, v in self.closed_options.items()}

    def _is_target_element(self, index):
        """Перевіряє, чи є елемент 'Closed'."""
        full_path = index.data(Qt.UserRole)
        return full_path and (full_path.endswith("/Boundary/Closed") or full_path.endswith("/AdjacentBoundary/Closed"))

    def createEditor(self, parent, option, index):
        if self._is_target_element(index):
            editor = QComboBox(parent)
            editor.addItems(self.items)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if self._is_target_element(index):
            code = index.model().data(index, Qt.EditRole)
            text_value = self.closed_options.get(code, "")
            idx = editor.findText(text_value)
            if idx != -1:
                editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        if self._is_target_element(index):

            selected_index = editor.currentIndex()
            if selected_index != -1:

                code = "true" if selected_index == 0 else "false"
                model.setData(index, code, Qt.EditRole)

    def displayText(self, value, locale):
        """Відображає 'Так'/'Ні' замість 'true'/'false'."""

        if isinstance(value, bool):
            value = str(value).lower()
        return self.closed_options.get(str(value), str(value))


class DispatcherDelegate(QStyledItemDelegate):
    """
    Делегат-диспетчер, який викликає відповідний спеціалізований делегат
    залежно від типу редагованого елемента.
    """

    def __init__(self, parent=None, state_act_delegate=None, category_delegate=None, purpose_delegate=None, ownership_delegate=None, doc_code_delegate=None, doc_type_delegate=None, land_code_delegate=None, closed_delegate=None):
        super().__init__(parent)

        self.state_act_delegate = state_act_delegate
        self.category_delegate = category_delegate
        self.purpose_delegate = purpose_delegate
        self.ownership_delegate = ownership_delegate
        self.land_code_delegate = land_code_delegate
        self.doc_code_delegate = doc_code_delegate
        self.doc_type_delegate = doc_type_delegate

        self.closed_delegate = closed_delegate

    def createEditor(self, parent, option, index):
        if self.state_act_delegate and self.state_act_delegate._is_target_element(index):
            return self.state_act_delegate.createEditor(parent, option, index)
        if self.category_delegate and self.category_delegate._is_target_element(index):
            return self.category_delegate.createEditor(parent, option, index)
        if self.purpose_delegate and self.purpose_delegate._is_target_element(index):
            editor = self.purpose_delegate.createEditor(parent, option, index)
            if editor:

                self.purpose_delegate.setModelData(
                    editor, index.model(), index)
            return None  # Не показуємо вбудований редактор
        if self.ownership_delegate and self.ownership_delegate._is_target_element(index):
            return self.ownership_delegate.createEditor(parent, option, index)
        if self.land_code_delegate and self.land_code_delegate._is_target_element(index):
            return self.land_code_delegate.createEditor(parent, option, index)
        if self.doc_code_delegate and self.doc_code_delegate._is_target_element(index):
            return self.doc_code_delegate.createEditor(parent, option, index)
        if self.doc_type_delegate and self.doc_type_delegate._is_target_element(index):
            return self.doc_type_delegate.createEditor(parent, option, index)
        if self.closed_delegate and self.closed_delegate._is_target_element(index):
            return self.closed_delegate.createEditor(parent, option, index)
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if self.state_act_delegate and self.state_act_delegate._is_target_element(index):
            return self.state_act_delegate.setEditorData(editor, index)
        if self.category_delegate and self.category_delegate._is_target_element(index):
            return self.category_delegate.setEditorData(editor, index)
        if self.purpose_delegate and self.purpose_delegate._is_target_element(index):
            return self.purpose_delegate.setEditorData(editor, index)
        if self.ownership_delegate and self.ownership_delegate._is_target_element(index):
            return self.ownership_delegate.setEditorData(editor, index)
        if self.land_code_delegate and self.land_code_delegate._is_target_element(index):
            return self.land_code_delegate.setEditorData(editor, index)
        if self.doc_code_delegate and self.doc_code_delegate._is_target_element(index):
            return self.doc_code_delegate.setEditorData(editor, index)
        if self.doc_type_delegate and self.doc_type_delegate._is_target_element(index):
            return self.doc_type_delegate.setEditorData(editor, index)
        if self.closed_delegate and self.closed_delegate._is_target_element(index):
            return self.closed_delegate.setEditorData(editor, index)
        return super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if self.state_act_delegate and self.state_act_delegate._is_target_element(index):
            return self.state_act_delegate.setModelData(editor, model, index)
        if self.category_delegate and self.category_delegate._is_target_element(index):
            return self.category_delegate.setModelData(editor, model, index)
        if self.purpose_delegate and self.purpose_delegate._is_target_element(index):
            return self.purpose_delegate.setModelData(editor, model, index)
        if self.ownership_delegate and self.ownership_delegate._is_target_element(index):
            return self.ownership_delegate.setModelData(editor, model, index)
        if self.land_code_delegate and self.land_code_delegate._is_target_element(index):
            return self.land_code_delegate.setModelData(editor, model, index)
        if self.doc_code_delegate and self.doc_code_delegate._is_target_element(index):
            return self.doc_code_delegate.setModelData(editor, model, index)
        if self.doc_type_delegate and self.doc_type_delegate._is_target_element(index):
            return self.doc_type_delegate.setModelData(editor, model, index)
        if self.closed_delegate and self.closed_delegate._is_target_element(index):
            return self.closed_delegate.setModelData(editor, model, index)
        return super().setModelData(editor, model, index)

    def displayText(self, value, locale):

        return super().displayText(value, locale)

    def initStyleOption(self, option, index):
        """Встановлює текст для відображення на основі делегата."""
        super().initStyleOption(option, index)

        if index.isValid() and index.column() == 1:

            try:
                full_path = index.data(Qt.UserRole) or ""
                schema_path = re.sub(r"\[\d+\]", "", str(full_path))
                if schema_path.endswith("DocumentList") and self.doc_code_delegate:
                    code = index.model().data(index, Qt.EditRole)
                    option.text = self.doc_code_delegate.doc_list.get(str(code), str(option.text))
                    return
            except Exception:
                pass

            if self.doc_code_delegate and self.doc_code_delegate._is_target_element(index):
                option.text = self.doc_code_delegate.displayText(option.text, option.locale)
            elif self.doc_type_delegate and self.doc_type_delegate._is_target_element(index):
                option.text = self.doc_type_delegate.displayText(
                    option.text, option.locale)
            elif self.closed_delegate and self.closed_delegate._is_target_element(index):
                option.text = self.closed_delegate.displayText(
                    option.text, option.locale)
