

import re
import os
import datetime
import webbrowser
from pathlib import Path
from docxtpl import DocxTemplate
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog, QDialog
from lxml import etree
from qgis.PyQt.QtCore import QUrl

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

        if not self.dockwidget.current_xml:
            QMessageBox.warning(self.dockwidget, "Помилка",
                                "Немає активного XML-файлу. Будь ласка, відкрийте або створіть файл.")
            return

        if not self.dockwidget.isVisible():
            self.dockwidget.show()
            self.dockwidget.raise_()

        if doc_type == "restoration_title1":
            self._generate_restoration_title1(template_name)
        elif doc_type == "restoration_title2":
            self._generate_restoration_title2(template_name)
        elif doc_type == "restoration_note":
            self._generate_restoration_explanation(template_name)
        else:
            QMessageBox.information(
                self.dockwidget, "У розробці", "Даний функціонал у розробці.")

    def _generate_restoration_title1(self, template_name):
        """
        Генерує титульну сторінку №1 для документації з відновлення меж.
        """

        current_xml = self.dockwidget.current_xml
        tree = current_xml.tree

        template_path = os.path.join(
            self.plugin_dir, 'templates', template_name)
        if not os.path.exists(template_path):
            QMessageBox.critical(self.dockwidget, "Помилка",
                                 f"Файл шаблону не знайдено: {template_path}")
            return

        context = self._get_base_context(tree)

        executors = tree.findall('.//InfoLandWork/Executor/Executor')
        if len(executors) > 0:
            executor1 = executors[0]
            context['QualificationNumber1'] = executor1.findtext(
                'Qualification/QualificationNumber', '')
            context['QualificationDate1'] = executor1.findtext(
                'Qualification/QualificationDate', '')
            context['ExecutorName1'] = self._get_full_name(
                executor1.find('ExecutorName'))
            context['ExecutorPhone'] = executor1.findtext(
                'ContactInfo/Phone', '')
        if len(executors) > 1:
            executor2 = executors[1]
            context['QualificationNumber2'] = executor2.findtext(
                'Qualification/QualificationNumber', '')
            context['QualificationDate2'] = executor2.findtext(
                'Qualification/QualificationDate', '')
            context['ExecutorName2'] = self._get_full_name(
                executor2.find('ExecutorName'))

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

        template_path = os.path.join(
            self.plugin_dir, 'templates', template_name)
        if not os.path.exists(template_path):
            QMessageBox.critical(self.dockwidget, "Помилка",
                                 f"Файл шаблону не знайдено: {template_path}")
            return

        context = self._get_base_context(tree)

        proprietor_info = tree.find('.//ParcelInfo/Proprietors/ProprietorInfo')
        contract_info_str = self._get_or_create_additional_info(
            parent_element=proprietor_info,
            info_type="Договір на виконання землевпорядних робіт",
            prefix="Договір на виконання землевпорядних робіт №",
            prompt_title="Договір на виконання робіт",
            prompt_text="В XML-файлі відсутня інформація про договір на виконання землевпорядних робіт.\n\nБажаєте додати її зараз?"
        )
        if not contract_info_str:
            log_msg(
                logFile, "Створення титулки 2 скасовано, оскільки не введено дані про договір.")
            return

        context['ReasonInfo'] = contract_info_str.replace(
            "Договір на виконання землевпорядних робіт №", "Договору на виконання землевпорядних робіт №")
        context['Zone'] = tree.findtext(
            './/CadastralZoneInfo/CadastralZoneNumber', '')
        context['Quarter'] = tree.findtext(
            './/CadastralQuarterInfo/CadastralQuarterNumber', '')
        context['Parcel'] = tree.findtext('.//ParcelMetricInfo/ParcelID', '')

        chief_name_element = tree.find(
            './/InfoLandWork/Executor/Chief/ChiefName')
        context['ExecutorChief'] = self._get_initials_and_lastname(
            chief_name_element)

        executor_name_element = tree.find(
            './/InfoLandWork/Executor/Executor/ExecutorName')
        context['ExecutorExecutor'] = self._get_initials_and_lastname(
            executor_name_element)

        doc = DocxTemplate(template_path)
        doc.render(context)

        xml_dir = os.path.dirname(current_xml.path)
        base_name = os.path.splitext(os.path.basename(current_xml.path))[0]
        output_filename = f"{base_name}_{os.path.splitext(template_name)[0]}.docx"
        output_path = os.path.join(xml_dir, output_filename)

        self._save_and_open_doc(doc, output_path)

    def _generate_restoration_explanation(self, template_name):
        """Генерує пояснюючу записку для документації з відновлення меж."""

        current_xml = self.dockwidget.current_xml
        tree = current_xml.tree

        template_path = os.path.join(
            self.plugin_dir, 'templates', template_name)
        if not os.path.exists(template_path):
            QMessageBox.critical(self.dockwidget, "Помилка",
                                 f"Файл шаблону не знайдено: {template_path}")
            return

        context = self._get_base_context(tree)

        context['ParcelOwnerBorn'] = bornPIB(context.get('ParcelOwner', ''))

        location_element = tree.find('.//ParcelLocationInfo/ParcelLocation')
        formatted_address = ""
        if location_element is not None:
            if location_element.find('Urban') is not None:

                parcel_region = context.get('ParcelRegion', '')
                parcel_district = context.get('ParcelDistrict', '')
                parcel_settlement = context.get('ParcelSettlement', '')
                parcel_street = context.get('ParcelStreetName', '')
                parcel_building = context.get('ParcelBuilding', '')
                address_parts = [f"за адресою: {parcel_region}, ", f"{parcel_district} район,",
                                 f"с. {parcel_settlement},", f"вул. {parcel_street}", f"№ {parcel_building}"]

                formatted_address = " ".join(filter(None, address_parts))
            elif location_element.find('Rural') is not None:

                parcel_region = to_genitive(context.get('ParcelRegion', ''))
                parcel_district = to_genitive(
                    context.get('ParcelDistrict', ''))
                parcel_settlement = to_genitive(
                    context.get('ParcelSettlement', ''))
                address_parts = [
                    f"за межами населеного пункту {parcel_settlement}", f"{parcel_district} району", f"{parcel_region} області"]
                formatted_address = " ".join(filter(None, address_parts))

        context['FormattedParcelAddress'] = formatted_address

        land_category_code = tree.findtext(
            './/CategoryPurposeInfo/Category', '')
        context['LandCategoryCode'] = land_category_code
        if land_category_code and 'LandCategories' in config:
            categories = dict(config['LandCategories'])
            context['LandCategoryText'] = categories.get(
                land_category_code, '')
        else:
            context['LandCategoryText'] = ''

        context['Area'] = tree.findtext('.//ParcelMetricInfo/Area/Size', '')

        purpose_code = tree.findtext('.//CategoryPurposeInfo/Purpose', '')
        context['PurposeCode'] = purpose_code

        context['LandUseCode'] = purpose_code

        purpose_text_raw = ''
        if purpose_code:
            subchapters = dict(config['LandPurposeSubchapters'])
            purpose_text_raw = subchapters.get(purpose_code, '')

        context['PurposeText'] = purpose_text_raw

        context['LandUseText'] = purpose_text_raw
        context['LandPurposeText'] = purpose_text_raw[0].lower(
        ) + purpose_text_raw[1:] if purpose_text_raw else ''

        context['PurposeDoc'] = tree.findtext(
            './/CategoryPurposeInfo/Use', 'не встановлено')

        executors = tree.findall('.//InfoLandWork/Executor/Executor')
        if len(executors) > 0:
            executor1 = executors[0]
            context['QualificationNumber1'] = executor1.findtext(
                'Qualification/QualificationNumber', '')
            context['QualificationDate1'] = executor1.findtext(
                'Qualification/QualificationDate', '')
            context['ExecutorName1'] = self._get_full_name(
                executor1.find('ExecutorName'))
            context['ExecutorPhone'] = executor1.findtext(
                'ContactInfo/Phone', '')
        if len(executors) > 1:
            executor2 = executors[1]
            context['QualificationNumber2'] = executor2.findtext(
                'Qualification/QualificationNumber', '')
            context['QualificationDate2'] = executor2.findtext(
                'Qualification/QualificationDate', '')
            context['ExecutorName2'] = self._get_full_name(
                executor2.find('ExecutorName'))

        proprietor_info = tree.find('.//ParcelInfo/Proprietors/ProprietorInfo')
        contract_info_str = self._get_or_create_additional_info(
            parent_element=proprietor_info,
            info_type="Договір на виконання землевпорядних робіт",
            prefix="Договір на виконання землевпорядних робіт №",
            prompt_title="Договір на виконання робіт",
            prompt_text="В XML-файлі відсутня інформація про договір на виконання землевпорядних робіт.\n\nБажаєте додати її зараз?"
        )
        if not contract_info_str:
            log_msg(
                logFile, "Створення пояснюючої записки скасовано, оскільки не введено дані про договір.")
            return
        context['ReasonInfo'] = contract_info_str.replace(
            "Договір на виконання землевпорядних робіт №", "Договору на виконання землевпорядних робіт №")
        context['Zone'] = tree.findtext(
            './/CadastralZoneInfo/CadastralZoneNumber', '')
        context['Quarter'] = tree.findtext(
            './/CadastralQuarterInfo/CadastralQuarterNumber', '')
        context['Parcel'] = tree.findtext('.//ParcelMetricInfo/ParcelID', '')
        context['ExecutorChief'] = self._get_initials_and_lastname(
            tree.find('.//InfoLandWork/Executor/Chief/ChiefName'))
        context['ExecutorExecutor'] = self._get_initials_and_lastname(
            tree.find('.//InfoLandWork/Executor/Executor/ExecutorName'))

        rtk_contract_info_str = self._get_or_create_additional_info(
            parent_element=proprietor_info,
            info_type="Договір на RTK",
            prefix="Договір на RTK №",
            prompt_title="Інформація про договір RTK",
            prompt_text="В XML-файлі відсутня інформація про договір на надання послуг RTK.\n\nБажаєте додати її зараз?"
        )
        if not rtk_contract_info_str:
            log_msg(
                logFile, "Створення пояснюючої записки скасовано, оскільки не введено дані про договір RTK.")
            return
        context['RTKContractInfo'] = rtk_contract_info_str.replace(
            "Договір на RTK №", "Договору на RTK №")

        context['GPSReceiver'] = self._get_or_create_additional_info(proprietor_info, "Приймач GPS", "Приймач GPS ", has_date=False, has_sn=True,
                                                                     prompt_title="Дані про GPS приймач", prompt_text="В XML-файлі відсутня інформація про GPS приймач.\n\nБажаєте додати її зараз?")
        context['GPSCert'] = self._get_or_create_additional_info(proprietor_info, "Сертифікат калібрування приймача GPS", "Сертифікат калібрування приймача GPS №",
                                                                 prompt_title="Сертифікат GPS", prompt_text="В XML-файлі відсутня інформація про сертифікат калібрування GPS приймача.\n\nБажаєте додати її зараз?")
        context['Tachymeter'] = self._get_or_create_additional_info(proprietor_info, "Тахеометр", "Тахеометр ", has_date=False, has_sn=True,
                                                                    prompt_title="Дані про тахеометр", prompt_text="В XML-файлі відсутня інформація про тахеометр.\n\nБажаєте додати її зараз?")
        context['TachymeterCert'] = self._get_or_create_additional_info(proprietor_info, "Сертифікат калібрування тахеометра", "Сертифікат калібрування тахеометра №",
                                                                        prompt_title="Сертифікат тахеометра", prompt_text="В XML-файлі відсутня інформація про сертифікат калібрування тахеометра.\n\nБажаєте додати її зараз?")

        if not all([context.get(k) for k in ['GPSReceiver', 'GPSCert', 'Tachymeter', 'TachymeterCert']]):
            log_msg(
                logFile, "Створення пояснюючої записки скасовано, оскільки не введено повну інформацію про обладнання.")
            return

        summed_lands = {}
        total_land_area = 0.0
        lands_parcel_container = tree.find('.//LandsParcel')
        if lands_parcel_container is not None:
            land_parcels = lands_parcel_container.findall('LandParcelInfo')
            land_codes_dict = dict(config['LandsCode'])

            for land in land_parcels:
                land_code = land.findtext('LandCode', '')
                area_element = land.find('.//MetricInfo/Area/Size')
                area = float(
                    area_element.text) if area_element is not None and area_element.text else 0.0
                total_land_area += area

                if land_code in summed_lands:
                    summed_lands[land_code] += area
                else:
                    summed_lands[land_code] = area

        lands_data = [{
            'code': code, 'name': land_codes_dict.get(code, 'Невідомий код'), 'area': f"{total_area:.4f}"
        } for code, total_area in summed_lands.items()]

        context['lands'] = lands_data
        context['total_land_area'] = f"{total_land_area:.4f}"

        restrictions_list = []
        total_restriction_area = 0.0
        restrictions_container = tree.find('.//Restrictions')
        if restrictions_container is not None:

            from .topology import GeometryProcessor
            processor = GeometryProcessor(tree)

            for restriction in restrictions_container.findall('RestrictionInfo'):
                restriction_code = restriction.findtext('RestrictionCode', '')
                restriction_name = restriction.findtext('RestrictionName', '')

                area_m2 = 0.0
                externals_element = restriction.find('Externals')
                if externals_element is not None:
                    try:

                        area_m2 = processor.calculate_polygon_area(
                            externals_element)
                    except Exception as e:
                        log_msg(
                            logFile, f"Помилка при обчисленні площі обмеження '{restriction_code}': {e}")

                area_ha = area_m2 / 10000.0
                total_restriction_area += area_ha

                restrictions_list.append({
                    'code': restriction_code,
                    'name': restriction_name,
                    'area': f"{area_ha:.4f}"
                })

        context['restrictions'] = restrictions_list

        if not restrictions_list:
            context['no_restrictions_text'] = "Обмеження у використанні ділянки відсутні"
        else:
            context['no_restrictions_text'] = ""

        doc = DocxTemplate(template_path)
        doc.render(context)
        xml_dir = os.path.dirname(current_xml.path)
        base_name = os.path.splitext(os.path.basename(current_xml.path))[0]
        output_filename = f"{base_name}_{os.path.splitext(template_name)[0]}.docx"
        output_path = os.path.join(xml_dir, output_filename)
        self._save_and_open_doc(doc, output_path)

    def _get_base_context(self, tree):
        """Збирає базовий набір даних для контексту шаблонів."""

        zone_number_str = tree.findtext(
            './/InfoPart/CadastralZoneInfo/CadastralZoneNumber', '')
        msk_value = zone_number_str[:2] if zone_number_str else ''

        equipment_context = self._get_equipment_data(tree)

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
            'MSK': msk_value,  # Додаємо MSK до контексту
            **equipment_context,  # Додаємо всі змінні обладнання
        }

    def _get_equipment_data(self, tree):
        """Збирає та парсить дані про обладнання з AdditionalInfo."""
        equipment_context = {
            'ReceiverModel': '', 'ReceiverSN': '', 'ReceiverCertNo': '', 'ReceiverCertDate': '',
            'TotStatModel': '', 'TotStatSN': '', 'TotStatCertNo': '', 'TotStatCertDate': '',
        }

        additional_info_blocks = tree.findall('.//AdditionalInfoBlock')
        if not additional_info_blocks:
            log_msg(
                logFile, "Не знайдено жодного блоку 'AdditionalInfoBlock' у XML-файлі.")
            return equipment_context

        for block in additional_info_blocks:
            for info_element in block.findall('AdditionalInfo'):
                text = info_element.text.strip() if info_element.text else ''
                log_msg(logFile, f"Аналізуємо AdditionalInfo: '{text}'")

                match = re.match(r"Приймач GPS\s+(.+?)\s+SN\s+(.+)", text)
                if match:
                    equipment_context['ReceiverModel'] = match.group(1).strip()
                    equipment_context['ReceiverSN'] = match.group(2).strip()
                    continue

                match = re.match(
                    r"Сертифікат калібрування приймача GPS\s*(?:№\s*)?(.+?)\s+від\s+(.+)", text)
                if match:
                    equipment_context['ReceiverCertNo'] = match.group(
                        1).strip()
                    equipment_context['ReceiverCertDate'] = match.group(
                        2).strip()
                    continue

                match = re.match(r"Тахеометр\s+(.+?)\s+SN\s+(.+)", text)
                if match:
                    equipment_context['TotStatModel'] = match.group(1).strip()
                    equipment_context['TotStatSN'] = match.group(2).strip()
                    continue

                match = re.match(
                    r"Сертифікат калібрування тахеометра\s+№\s+(.+?)\s+від\s+(.+)", text)
                if match:
                    equipment_context['TotStatCertNo'] = match.group(1).strip()
                    equipment_context['TotStatCertDate'] = match.group(
                        2).strip()
                    continue

        return equipment_context

    def _save_and_open_doc(self, doc, output_path):
        """Зберігає та відкриває документ, обробляючи помилки доступу."""

        saved_successfully = False
        while not saved_successfully:
            try:
                doc.save(output_path)
                saved_successfully = True

                from qgis.PyQt.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))

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
                    log_msg(
                        logFile, "Збереження документа скасовано користувачем через помилку доступу.")
                    return  # Вихід з функції, якщо користувач натиснув "Скасувати"

    def _get_or_create_additional_info(self, parent_element, info_type, prefix, prompt_title="Введення даних", prompt_text="Бажаєте додати інформацію?", has_date=True, has_sn=False):
        """
        Універсальний метод для пошуку або створення додаткової інформації в XML.
        - parent_element: батьківський елемент для пошуку/додавання AdditionalInfoBlock (завжди ProprietorInfo).
        - info_type: повний опис інформації для діалогів (напр., "Договір на виконання землевпорядних робіт").
        - prefix: текстовий префікс для рядка в XML (напр., "Договір на виконання землевпорядних робіт №").
        - prompt_title: заголовок вікна запиту.
        - prompt_text: текст у вікні запиту.
        - has_date: чи потрібно запитувати дату.
        - has_sn: чи потрібно запитувати серійний номер (SN).
        """
        if parent_element is None:
            QMessageBox.warning(self.dockwidget, "Помилка структури XML",
                                f"Не знайдено розділ 'ProprietorInfo' для додавання інформації: '{info_type}'.")
            return None

        additional_info_block = parent_element.find('AdditionalInfoBlock')
        if additional_info_block is not None:
            for info_element in additional_info_block.findall('AdditionalInfo'):
                if info_element.text and info_element.text.strip().startswith(prefix):

                    return info_element.text.strip()

        reply = QMessageBox.question(
            self.dockwidget, prompt_title, prompt_text, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.No:
            return None

        parts = [prefix]

        label = "модель" if has_sn else "номер"
        num_or_model, ok = QInputDialog.getText(
            self.dockwidget, prompt_title, f"Введіть {label} для '{info_type}':")
        if not ok or not num_or_model.strip():
            QMessageBox.warning(self.dockwidget, "Відміна",
                                f"{label.capitalize()} не введено. Операцію скасовано.")
            return None
        parts.append(f"{num_or_model.strip()}")

        if has_sn:
            sn, ok = QInputDialog.getText(
                self.dockwidget, prompt_title, f"Введіть серійний номер (SN) для '{info_type}':")
            if not ok or not sn.strip():
                QMessageBox.warning(
                    self.dockwidget, "Відміна", "Серійний номер не введено. Операцію скасовано.")
                return None
            parts.append(f" SN {sn.strip()}")

        if has_date:
            date_dialog = DateInputDialog(parent=self.dockwidget)
            if date_dialog.exec_() == QDialog.Accepted:
                date_str = date_dialog.get_date()  # yyyy-MM-dd
                parts.append(f" від {date_str}")
            else:
                QMessageBox.warning(self.dockwidget, "Відміна",
                                    "Дату не вибрано. Операцію скасовано.")
                return None

        info_str = "".join(parts)

        if additional_info_block is None:
            additional_info_block = etree.SubElement(
                parent_element, "AdditionalInfoBlock")
        new_info_element = etree.SubElement(
            additional_info_block, "AdditionalInfo")
        new_info_element.text = info_str

        self.dockwidget.mark_as_changed()
        if hasattr(self.dockwidget.current_xml, 'tree_view'):
            self.dockwidget.current_xml.tree_view.rebuild_tree_view()

        log_msg(logFile, f"Додано інформацію '{info_type}': '{info_str}'")
        return info_str

    def _get_full_name(self, element):
        if element is None:
            return ""
        return f"{element.findtext('LastName', '')} {element.findtext('FirstName', '')} {element.findtext('MiddleName', '')}".strip()

    def _get_initials_and_lastname(self, element):
        """Форматує ПІБ у вигляд 'І. Б. Прізвище' або 'І. Прізвище'."""
        if element is None:
            return ""

        last_name = element.findtext('LastName', '')
        first_name = element.findtext('FirstName', '')
        middle_name = element.findtext('MiddleName', '')

        if not last_name:
            return ""

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
            natural_person = prop.find(
                './/Authentication/NaturalPerson/FullName')
            legal_entity_name = prop.findtext(
                './/Authentication/LegalEntity/Name')

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
                return "у межах населеного пункту"
            elif location_element.find('Rural') is not None:
                return "за межами населеного пункту"
        return ""
