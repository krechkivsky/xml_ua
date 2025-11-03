# -*- coding: utf-8 -*-
# documents.py

import re
import os
import datetime
import webbrowser
from docxtpl import DocxTemplate
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog, QDialog
from lxml import etree

from .common import log_msg, logFile, config
from .date_dialog import DateInputDialog
from .cases import bornPIB, to_genitive

class DocumentGenerator:
    """
    Клас для генерації документів на основі шаблонів docx та даних з XML.
    """
    def __init__(self, dockwidget):
        self.dockwidget = dockwidget
        self.iface = dockwidget.iface
        self.plugin_dir = dockwidget.plugin.plugin_dir

    def generate_document(self, doc_type, template_name):
        """
        Основний метод-диспетчер для генерації документів.
        """
        log_msg(logFile, f"'{doc_type}': '{template_name}'")
        if not self.dockwidget.current_xml:
            QMessageBox.warning(self.dockwidget, "Помилка", "Немає активного XML-файлу. Будь ласка, відкрийте або створіть файл.")
            return

        # Якщо віджет прихований, робимо його видимим
        if not self.dockwidget.isVisible():
            self.dockwidget.show()
            self.dockwidget.raise_()

        # Диспетчер для виклику відповідних методів
        if doc_type == "restoration_title1":
            self._generate_restoration_title1(template_name)
        elif doc_type == "restoration_title2":
            self._generate_restoration_title2(template_name)
        elif doc_type == "restoration_note":
            self._generate_restoration_explanation(template_name)
        else:
            QMessageBox.information(self.dockwidget, "У розробці", "Даний функціонал у розробці.")

    def _generate_restoration_title1(self, template_name):
        """
        Генерує титульну сторінку №1 для документації з відновлення меж.
        """
        log_msg(logFile, f"Генерація документа з шаблону: {template_name}")
        
        current_xml = self.dockwidget.current_xml
        tree = current_xml.tree
        
        # 1. Шлях до шаблону
        template_path = os.path.join(self.plugin_dir, 'templates', template_name)
        if not os.path.exists(template_path):
            QMessageBox.critical(self.dockwidget, "Помилка", f"Файл шаблону не знайдено: {template_path}")
            return

        # 2. Збір базового контексту з XML
        context = self._get_base_context(tree)

        # --- Дані про виконавців (інженерів) ---
        executors = tree.findall('.//InfoLandWork/Executor/Executor')
        # --- Початок змін: Виправлення логіки збору даних для двох виконавців ---
        if len(executors) > 0:
            executor1 = executors[0]
            context['QualificationNumber1'] = executor1.findtext('Qualification/QualificationNumber', '')
            context['QualificationDate1'] = executor1.findtext('Qualification/QualificationDate', '')
            context['ExecutorName1'] = self._get_full_name(executor1.find('ExecutorName'))
            context['ExecutorPhone'] = executor1.findtext('ContactInfo/Phone', '')

        if len(executors) > 1:
            executor2 = executors[1]
            context['QualificationNumber2'] = executor2.findtext('Qualification/QualificationNumber', '')
            context['QualificationDate2'] = executor2.findtext('Qualification/QualificationDate', '')
            context['ExecutorName2'] = self._get_full_name(executor2.find('ExecutorName'))
        # --- Кінець змін ---



        # 3. Рендеринг шаблону та збереження
        doc = DocxTemplate(template_path)
        doc.render(context)

        xml_dir = os.path.dirname(current_xml.path)
        base_name = os.path.splitext(os.path.basename(current_xml.path))[0]
        output_filename = f"{base_name}_{os.path.splitext(template_name)[0]}.docx"
        output_path = os.path.join(xml_dir, output_filename)

        self._save_and_open_doc(doc, output_path)

    def _generate_restoration_title2(self, template_name):
        """Генерує титульну сторінку №2 для документації з відновлення меж."""
        log_msg(logFile, f"Титульна сторінка №2 з шаблону: '{template_name}'")

        current_xml = self.dockwidget.current_xml
        tree = current_xml.tree

        # 1. Шлях до шаблону
        template_path = os.path.join(self.plugin_dir, 'templates', template_name)
        if not os.path.exists(template_path):
            QMessageBox.critical(self.dockwidget, "Помилка", f"Файл шаблону не знайдено: {template_path}")
            return

        # 2. Збір базового контексту
        context = self._get_base_context(tree)

        # 3. Пошук або створення інформації про договір
        contract_info_str = self._get_or_create_reason_info(tree)
        if not contract_info_str:
            log_msg(logFile, "Створення титулки 2 скасовано, оскільки не введено дані про договір.")
            return

        # 4. Додавання додаткових полів до контексту
        context['ReasonInfo'] = contract_info_str
        context['Zone'] = tree.findtext('.//CadastralZoneInfo/CadastralZoneNumber', '')
        context['Quarter'] = tree.findtext('.//CadastralQuarterInfo/CadastralQuarterNumber', '')
        context['Parcel'] = tree.findtext('.//ParcelMetricInfo/ParcelID', '')

        chief_name_element = tree.find('.//InfoLandWork/Executor/Chief/ChiefName')
        context['ExecutorChief'] = self._get_initials_and_lastname(chief_name_element)

        # Припускаємо, що потрібен перший виконавець
        executor_name_element = tree.find('.//InfoLandWork/Executor/Executor/ExecutorName')
        context['ExecutorExecutor'] = self._get_initials_and_lastname(executor_name_element)

        # 5. Рендеринг шаблону та збереження
        doc = DocxTemplate(template_path)
        doc.render(context)

        xml_dir = os.path.dirname(current_xml.path)
        base_name = os.path.splitext(os.path.basename(current_xml.path))[0]
        output_filename = f"{base_name}_{os.path.splitext(template_name)[0]}.docx"
        output_path = os.path.join(xml_dir, output_filename)

        self._save_and_open_doc(doc, output_path)

    def _generate_restoration_explanation(self, template_name):
        """Генерує пояснюючу записку для документації з відновлення меж."""
        log_msg(logFile, f"Генерація пояснюючої записки з шаблону: '{template_name}'")

        current_xml = self.dockwidget.current_xml
        tree = current_xml.tree

        # 1. Шлях до шаблону
        template_path = os.path.join(self.plugin_dir, 'templates', template_name)
        if not os.path.exists(template_path):
            QMessageBox.critical(self.dockwidget, "Помилка", f"Файл шаблону не знайдено: {template_path}")
            return

        # 2. Збір об'єднаного контексту
        # Починаємо з базового контексту
        context = self._get_base_context(tree)

        # Додаємо відмінювання ПІБ власника
        context['ParcelOwnerBorn'] = bornPIB(context.get('ParcelOwner', ''))

        # --- Початок змін: Формування повної адреси ділянки ---
        location_element = tree.find('.//ParcelLocationInfo/ParcelLocation')
        formatted_address = ""
        if location_element is not None:
            if location_element.find('Urban') is not None:
                # Формат для ділянки в межах населеного пункту
                parcel_region = context.get('ParcelRegion', '')
                parcel_district = context.get('ParcelDistrict', '')
                parcel_settlement = context.get('ParcelSettlement', '')
                parcel_street = context.get('ParcelStreetName', '')
                parcel_building = context.get('ParcelBuilding', '')
                address_parts = [f"за адресою: {parcel_region}, ", f"{parcel_district} район,", f"с. {parcel_settlement},", f"вул. {parcel_street}", f"№ {parcel_building}"]
                formatted_address = " ".join(filter(None, address_parts)) # З'єднуємо, ігноруючи порожні частини
            elif location_element.find('Rural') is not None:
                # Формат для ділянки за межами населеного пункту
                parcel_region = to_genitive(context.get('ParcelRegion', ''))
                parcel_district = to_genitive(context.get('ParcelDistrict', ''))
                parcel_settlement = to_genitive(context.get('ParcelSettlement', ''))
                address_parts = [f"за межами населеного пункту {parcel_settlement}", f"{parcel_district} району", f"{parcel_region} області"]
                formatted_address = " ".join(filter(None, address_parts))

        context['FormattedParcelAddress'] = formatted_address
        # --- Кінець змін ---

        # --- Початок змін: Додавання коду та назви категорії земель ---
        land_category_code = tree.findtext('.//CategoryPurposeInfo/Category', '')
        context['LandCategoryCode'] = land_category_code
        if land_category_code and 'LandCategories' in config:
            categories = dict(config['LandCategories'])
            context['LandCategoryText'] = categories.get(land_category_code, '')
        else:
            context['LandCategoryText'] = ''
        # --- Кінець змін ---

        # --- Початок змін: Додавання коду та назви цільового призначення (використання) ---
        purpose_code = tree.findtext('.//CategoryPurposeInfo/Purpose', '')
        context['LandUseCode'] = purpose_code

        if purpose_code:
            subchapters = dict(config['LandPurposeSubchapters'])
            purpose_text_raw = subchapters.get(purpose_code, '')
            context['LandUseText'] = purpose_text_raw # Додаємо повний текст

            if purpose_text_raw:
                # Для сумісності залишаємо LandPurposeText з маленької літери
                context['LandPurposeText'] = purpose_text_raw[0].lower() + purpose_text_raw[1:]
            else:
                context['LandPurposeText'] = ''
        else:
            context['LandUseText'] = ''
            context['LandPurposeText'] = ''
        # --- Кінець змін ---

        # Додаємо дані з титульної сторінки 1 (виконавці)
        executors = tree.findall('.//InfoLandWork/Executor/Executor')
        if len(executors) > 0:
            executor1 = executors[0]
            context['QualificationNumber1'] = executor1.findtext('Qualification/QualificationNumber', '')
            context['QualificationDate1'] = executor1.findtext('Qualification/QualificationDate', '')
            context['ExecutorName1'] = self._get_full_name(executor1.find('ExecutorName'))
            context['ExecutorPhone'] = executor1.findtext('ContactInfo/Phone', '')
        if len(executors) > 1:
            executor2 = executors[1]
            context['QualificationNumber2'] = executor2.findtext('Qualification/QualificationNumber', '')
            context['QualificationDate2'] = executor2.findtext('Qualification/QualificationDate', '')
            context['ExecutorName2'] = self._get_full_name(executor2.find('ExecutorName'))

        # Додаємо дані з титульної сторінки 2
        contract_info_str = self._get_or_create_reason_info(tree)
        if not contract_info_str:
            log_msg(logFile, "Створення пояснюючої записки скасовано, оскільки не введено дані про договір.")
            return
        context['ReasonInfo'] = contract_info_str
        context['Zone'] = tree.findtext('.//CadastralZoneInfo/CadastralZoneNumber', '')
        context['Quarter'] = tree.findtext('.//CadastralQuarterInfo/CadastralQuarterNumber', '')
        context['Parcel'] = tree.findtext('.//ParcelMetricInfo/ParcelID', '')
        context['ExecutorChief'] = self._get_initials_and_lastname(tree.find('.//InfoLandWork/Executor/Chief/ChiefName'))
        context['ExecutorExecutor'] = self._get_initials_and_lastname(tree.find('.//InfoLandWork/Executor/Executor/ExecutorName'))

        # 3. Рендеринг, збереження та відкриття
        doc = DocxTemplate(template_path)
        doc.render(context)
        xml_dir = os.path.dirname(current_xml.path)
        base_name = os.path.splitext(os.path.basename(current_xml.path))[0]
        output_filename = f"{base_name}_{os.path.splitext(template_name)[0]}.docx"
        output_path = os.path.join(xml_dir, output_filename)
        self._save_and_open_doc(doc, output_path)

    def _get_base_context(self, tree):
        """Збирає базовий набір даних для контексту шаблонів."""
        return {
            'ExecutorCompanyName': tree.findtext('.//InfoLandWork/Executor/CompanyName', ''),
            'ExecutorRegion': tree.findtext('.//InfoLandWork/Executor/Address/Region', ''),
            'ExecutorSettlement': tree.findtext('.//InfoLandWork/Executor/Address/Settlement', ''),
            'ExecutorStreet': tree.findtext('.//InfoLandWork/Executor/Address/Street', ''),
            'ExecutorApt': tree.findtext('.//InfoLandWork/Executor/Address/Building', ''),
            'ParcelOwner': self._get_parcel_owners(tree),
            'ParcelLocation': self._get_parcel_location(tree),
            'ParcelRegion': tree.findtext('.//ParcelLocationInfo/Region', ''),
            'ParcelSettlement': tree.findtext('.//ParcelLocationInfo/Settlement', ''),
            'ParcelDistrict': tree.findtext('.//ParcelLocationInfo/District', ''),
            'ParcelStreetName': tree.findtext('.//ParcelLocationInfo/ParcelAddress/StreetName', ''),
            'ParcelBuilding': tree.findtext('.//ParcelLocationInfo/ParcelAddress/Building', ''),
            'CurrentYear': datetime.datetime.now().year,
        }

    def _save_and_open_doc(self, doc, output_path):
        """Зберігає та відкриває документ, обробляючи помилки доступу."""
        # --- Початок змін: Обробка помилки доступу при збереженні ---
        saved_successfully = False
        while not saved_successfully:
            try:
                doc.save(output_path)
                saved_successfully = True
                log_msg(logFile, f"Документ збережено: {output_path}")
                
                # 5. Відкриття файлу
                webbrowser.open(output_path)

            except PermissionError:
                reply = QMessageBox.warning(
                    self.dockwidget,
                    "Помилка збереження",
                    f"Не вдалося зберегти файл:\n\n{output_path}\n\n"
                    "Можливо, цей файл вже відкритий в іншій програмі (наприклад, MS Word). "
                    "Будь ласка, закрийте його та спробуйте ще раз.",
                    QMessageBox.Retry | QMessageBox.Cancel,
                    QMessageBox.Retry
                )
                if reply == QMessageBox.Cancel:
                    log_msg(logFile, "Збереження документа скасовано користувачем через помилку доступу.")
                    return # Вихід з функції, якщо користувач натиснув "Скасувати"
        # --- Кінець змін ---

    def _get_or_create_reason_info(self, tree):
        """Шукає інформацію про договір або запитує її у користувача і додає в XML."""
        proprietor_info = tree.find('.//ParcelInfo/Proprietors/ProprietorInfo')
        if proprietor_info is None:
            QMessageBox.warning(self.dockwidget, "Помилка", "Не знайдено розділ 'ProprietorInfo' для додавання інформації про підставу виконання робіт.")
            return None

        # --- Початок змін: Пошук будь-якої з підстав ---
        # Шукаємо існуючий запис про договір, рішення або дозвіл
        reason_pattern = re.compile(r"(Договір|Рішення|Дозвіл) №.* від .* р\.")
        additional_info_block = proprietor_info.find('AdditionalInfoBlock')
        if additional_info_block is not None:
            for info_element in additional_info_block.findall('AdditionalInfo'):
                if info_element.text and reason_pattern.match(info_element.text.strip()):
                    log_msg(logFile, f"Знайдено існуючу інформацію про підставу: '{info_element.text.strip()}'")
                    return info_element.text.strip()

        # Якщо не знайдено, запитуємо у користувача
        reply = QMessageBox.question(self.dockwidget, "Інформація про підставу",
                                     "В XML-файлі відсутня інформація про підставу виконання робіт (договір, рішення, дозвіл).\n\n"
                                     "Бажаєте додати її зараз?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.No:
            return None

        # Запит типу підстави
        reason_types = ["Договір", "Рішення", "Дозвіл"]
        reason_type, ok_type = QInputDialog.getItem(self.dockwidget, "Вибір підстави", "Виберіть тип підстави:", reason_types, 0, False)
        if not ok_type or not reason_type:
            QMessageBox.warning(self.dockwidget, "Відміна", "Тип підстави не вибрано. Операцію скасовано.")
            return None

        # Запит номера
        reason_num, ok_num = QInputDialog.getText(self.dockwidget, "Введення даних", f"Введіть номер ({reason_type.lower()}):")
        if not ok_num or not reason_num.strip():
            QMessageBox.warning(self.dockwidget, "Відміна", f"Номер ({reason_type.lower()}) не введено. Операцію скасовано.")
            return None

        date_dialog = DateInputDialog(parent=self.dockwidget)
        if date_dialog.exec_() == QDialog.Accepted:
            reason_date_str = date_dialog.get_date() # yyyy-MM-dd
            contract_date_obj = datetime.datetime.strptime(reason_date_str, "%Y-%m-%d")
            formatted_date = contract_date_obj.strftime("%d.%m.%Y")
        else:
            QMessageBox.warning(self.dockwidget, "Відміна", "Дату не вибрано. Операцію скасовано.")
            return None

        # Формуємо рядок
        reason_info_str = f"{reason_type} №{reason_num.strip()} від {formatted_date} р."
        # --- Кінець змін ---

        # Додаємо елементи в XML
        if additional_info_block is None:
            additional_info_block = etree.SubElement(proprietor_info, "AdditionalInfoBlock")

        new_info_element = etree.SubElement(additional_info_block, "AdditionalInfo")
        new_info_element.text = reason_info_str

        # Позначаємо зміни та оновлюємо дерево
        self.dockwidget.mark_as_changed()
        if hasattr(self.dockwidget.current_xml, 'tree_view'):
            self.dockwidget.current_xml.tree_view.rebuild_tree_view()

        log_msg(logFile, f"Додано інформацію про підставу: '{reason_info_str}'")
        return reason_info_str

    def _get_full_name(self, element):
        if element is None: return ""
        return f"{element.findtext('LastName', '')} {element.findtext('FirstName', '')} {element.findtext('MiddleName', '')}".strip()

    def _get_initials_and_lastname(self, element):
        """Форматує ПІБ у вигляд 'І. Б. Прізвище'."""
        if element is None: return ""
        last_name = element.findtext('LastName', '')
        first_name = element.findtext('FirstName', '')
        middle_name = element.findtext('MiddleName', '')
        
        initials = []
        if first_name:
            initials.append(f"{first_name[0]}.")
        if middle_name:
            initials.append(f"{middle_name[0]}.")
            
        return f"{' '.join(initials)} {last_name}".strip()

    def _get_parcel_owners(self, tree):
        """Збирає імена всіх власників і повертає їх у вигляді рядка."""
        owners = []
        proprietors = tree.findall('.//ParcelInfo/Proprietors/ProprietorInfo')
        for prop in proprietors:
            natural_person = prop.find('.//Authentication/NaturalPerson/FullName')
            legal_entity_name = prop.findtext('.//Authentication/LegalEntity/Name')

            if natural_person is not None:
                owners.append(self._get_full_name(natural_person))
            elif legal_entity_name:
                owners.append(legal_entity_name.strip())
        
        return ",\n".join(filter(None, owners))

    def _get_parcel_location(self, tree):
        """Визначає місцезнаходження ділянки (в межах/за межами)."""
        location_element = tree.find('.//ParcelLocationInfo/ParcelLocation')
        if location_element is not None:
            if location_element.find('Urban') is not None:
                return "У межах населеного пункту"
            elif location_element.find('Rural') is not None:
                return "За межами населеного пункту"
        return ""