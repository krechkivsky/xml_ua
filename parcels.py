# -*- coding: utf-8 -*-
# parcels.py

import os
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPolygon,
    QgsLineString,
    QgsPointXY,
    QgsProject,
    QgsLayerTreeLayer,
    QgsEditorWidgetSetup
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from lxml import etree
from .common import log_msg, category_map, purpose_map, code_map, insert_element_in_order
from .common import logFile

class CadastralParcel:
    """Клас для обробки земельної ділянки з XML-файлу."""

    def __init__(self, root, crs_epsg, group, plugin_dir, layers_root, lines_to_coords_func, xml_ua_layers_instance):
        """
        Ініціалізація об'єкта для роботи з земельною ділянкою.

        Args:
            root: Кореневий елемент XML-дерева.
            crs_epsg (str): EPSG-код системи координат.
            group (QgsLayerTreeGroup): Група шарів у QGIS.
            plugin_dir (str): Шлях до директорії плагіна.
            layers_root (QgsLayerTreeGroup): Кореневий вузол дерева шарів QGIS.
            lines_to_coords_func (function): Функція для перетворення ліній у координати.
            xml_ua_layers_instance: Екземпляр класу xmlUaLayers для доступу до його методів.
        """
        self.root = root
        self.crs_epsg = crs_epsg
        self.group = group
        self.plugin_dir = plugin_dir
        self.layers_root = layers_root
        self.lines_to_coords = lines_to_coords_func
        self.xml_ua_layers = xml_ua_layers_instance

    def _coord_to_polygon(self, coordinates):
        """Формує полігон із заданого списку координат."""
        if not coordinates:
            return QgsPolygon()
        # Координати в XML (X, Y) відповідають (Y, X) в QGIS
        line_string = QgsLineString([QgsPointXY(p.y(), p.x()) for p in coordinates])
        polygon = QgsPolygon(line_string)
        return polygon

    def _get_determination_method_label(self):
        """Отримує текстове представлення методу визначення площі."""
        from .common import area_determination_map
        det_elem = self.root.find(".//ParcelMetricInfo/Area/DeterminationMethod")
        if det_elem is None or not len(det_elem):
            return ""

        if det_elem.find("ExchangeFileCoordinates") is not None:
            return area_determination_map.get("<ExhangeFileCoordinates/>", "За координатами обмінного файлу")
        if det_elem.find("DocExch") is not None:
            return area_determination_map.get("<DocExch/>", "Згідно із правовстановлювальним документом")

        calculation = det_elem.find("Calculation/CoordinateSystem")
        if calculation is not None:
            if calculation.find("SC42") is not None:
                return area_determination_map.get("<Calculation><CoordinateSystem><SC42/></CoordinateSystem></Calculation>", "Переобчислення з 'СК-42' (6 град зона)")
            if calculation.find("SC42_3") is not None:
                return area_determination_map.get("<Calculation><CoordinateSystem><SC42_3/></CoordinateSystem></Calculation>", "Переобчислення з 'СК-42' (3 град зона)")
            if calculation.find("USC2000") is not None:
                return area_determination_map.get("<Calculation><CoordinateSystem><USC2000/></CoordinateSystem></Calculation>", "Переобчислення з 'УСК2000'")
            if calculation.find("WGS84") is not None:
                return area_determination_map.get("<Calculation><CoordinateSystem><WGS84/></CoordinateSystem></Calculation>", "Переобчислення з 'WGS84'")
            if calculation.find("Local") is not None:
                msk_text = calculation.findtext("Local", "").strip()
                return f"Переобчислення з місцевої системи координат '{msk_text}'"
            if calculation.find("SC63") is not None:
                sc63 = calculation.find("SC63")
                if sc63.find("X") is not None: return area_determination_map.get("<Calculation><CoordinateSystem><SC63><X/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-X'")
                if sc63.find("C") is not None: return area_determination_map.get("<Calculation><CoordinateSystem><SC63><C/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-C'")
                if sc63.find("P") is not None: return area_determination_map.get("<Calculation><CoordinateSystem><SC63><P/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-P'")
                if sc63.find("T") is not None: return area_determination_map.get("<Calculation><CoordinateSystem><SC63><T/></SC63></CoordinateSystem></Calculation>", "Переобчислення з 'SC63-T'")
        return "Невідомо"

    def add_parcel_layer(self):
        """Створює та заповнює шар 'Ділянка'."""
        parcel_infos = self.root.findall(".//Parcels/ParcelInfo")
        if not parcel_infos:
            log_msg(logFile, f"У файлі відсутній елемент ParcelInfo")
            return None

        if len(parcel_infos) > 1:
            log_msg(logFile, f"Знайдено {len(parcel_infos)} розділів ParcelInfo. Використовується перший.")

        parcel_info = parcel_infos[0]
        metric_info = parcel_info.find("ParcelMetricInfo")
        if metric_info is None:
            log_msg(logFile, "Відсутній елемент ParcelMetricInfo у першому ParcelInfo")
            return None

        layer = QgsVectorLayer(f"MultiPolygon?crs={self.crs_epsg}", "Ділянка", "memory")
        layer.loadNamedStyle(os.path.join(self.plugin_dir, "templates", "parcel.qml"))
        provider = layer.dataProvider()

        # Підключення сигналів
        layer.setCustomProperty("xml_layer_id", self.xml_ua_layers.id)
        layer.editingStopped.connect(self.xml_ua_layers.on_editing_stopped)
        layer.attributeValueChanged.connect(
            lambda fid, idx, val, l=layer: self.xml_ua_layers.handle_parcel_attribute_change(l, fid, idx, val)
        )

        # Опис полів
        fields = [
            QgsField("ParcelID", QVariant.String), QgsField("Description", QVariant.String),
            QgsField("AreaSize", QVariant.Double), QgsField("AreaUnit", QVariant.String),
            QgsField("DeterminationMethod", QVariant.String), QgsField("Region", QVariant.String),
            QgsField("Settlement", QVariant.String), QgsField("District", QVariant.String),
            QgsField("ParcelLocation", QVariant.String), QgsField("StreetType", QVariant.String),
            QgsField("StreetName", QVariant.String), QgsField("Building", QVariant.String),
            QgsField("Block", QVariant.String), QgsField("AdditionalInfo", QVariant.String),
            QgsField("Category", QVariant.String), QgsField("Purpose", QVariant.String),
            QgsField("Use", QVariant.String), QgsField("Code", QVariant.String),
        ]
        provider.addAttributes(fields)
        layer.updateFields()

        # Псевдоніми полів
        aliases = {
            "ParcelID": "Номер ділянки", "Description": "Опис", "AreaSize": "Площа",
            "AreaUnit": "Одиниця виміру", "DeterminationMethod": "Спосіб визначення площі",
            "Region": "Регіон", "Settlement": "Назва населеного пункту", "District": "Назва району",
            "ParcelLocation": "Відношення до населеного пункту", "StreetType": "Тип (вулиця, проспект, провулок тощо)",
            "StreetName": "Назва вулиці", "Building": "Номер будинку", "Block": "Номер корпусу",
            "AdditionalInfo": "Додаткова інформація", "Category": "Категорія земель",
            "Purpose": "Цільове призначення (використання)", "Use": "Цільове призначення згідно із документом",
            "Code": "Код форми власності",
        }
        for field_name, alias in aliases.items():
            layer.setFieldAlias(layer.fields().indexOf(field_name), alias)

        # Налаштування віджетів
        setup_category = QgsEditorWidgetSetup("ValueMap", {"map": category_map, "UseMap": "true"})
        layer.setEditorWidgetSetup(layer.fields().indexOf("Category"), setup_category)

        setup_purpose = QgsEditorWidgetSetup("ValueMap", {"map": purpose_map, "UseMap": "true"})
        layer.setEditorWidgetSetup(layer.fields().indexOf("Purpose"), setup_purpose)

        setup_code = QgsEditorWidgetSetup("ValueMap", {"map": code_map, "UseMap": "true"})
        layer.setEditorWidgetSetup(layer.fields().indexOf("Code"), setup_code)

        determination_variants = [
            "За координатами обмінного файлу", "Згідно із правовстановлювальним документом",
            "Переобчислення з 'СК-42' (6 град зона)", "Переобчислення з 'СК-42' (3 град зона)",
            "Переобчислення з 'УСК2000'", "Переобчислення з 'WGS84'", "Переобчислення з 'SC63-X'",
            "Переобчислення з 'SC63-C'", "Переобчислення з 'SC63-P'", "Переобчислення з 'SC63-T'",
            "Переобчислення з місцевої системи координат"
        ]
        value_map_det = {v: v for v in determination_variants}
        setup_det = QgsEditorWidgetSetup("ValueMap", {"map": value_map_det, "UseMap": "true"})
        layer.setEditorWidgetSetup(layer.fields().indexOf("DeterminationMethod"), setup_det)

        # Значення полів
        parcel_id = metric_info.findtext("ParcelID", "")
        description = metric_info.findtext("Description", "")
        area_size = metric_info.findtext("Area/Size", "")
        area_unit = metric_info.findtext("Area/MeasurementUnit", "")
        area_method = self._get_determination_method_label()

        location_info = parcel_info.find("ParcelLocationInfo")
        region = location_info.findtext("Region", "") if location_info is not None else ""
        settlement = location_info.findtext("Settlement", "") if location_info is not None else ""
        district = location_info.findtext("District", "") if location_info is not None else ""
        
        parcel_location_elem = location_info.find("ParcelLocation") if location_info is not None else None
        parcel_location = ""
        if parcel_location_elem is not None:
            if parcel_location_elem.find("Rural") is not None:
                parcel_location = "За межами населеного пункту"
            elif parcel_location_elem.find("Urban") is not None:
                parcel_location = "У межах населеного пункту"

        address_info = location_info.find("ParcelAddress") if location_info is not None else None
        street_type = address_info.findtext("StreetType", "") if address_info is not None else ""
        street_name = address_info.findtext("StreetName", "") if address_info is not None else ""
        building = address_info.findtext("Building", "") if address_info is not None else ""
        block = address_info.findtext("Block", "") if address_info is not None else ""

        additional_info = parcel_info.findtext("AdditionalInfoBlock/AdditionalInfo", "")
        category_purpose_info = parcel_info.find("CategoryPurposeInfo")

        # --- Початок змін: Забезпечення наявності та порядку елементів у CategoryPurposeInfo ---
        if category_purpose_info is not None:
            category = category_purpose_info.findtext("Category", "")
            purpose = category_purpose_info.findtext("Purpose", "")
            
            use_element = category_purpose_info.find("Use")
            if use_element is None:
                # Якщо елемент 'Use' відсутній, створюємо його
                use_element = etree.SubElement(category_purpose_info, "Use")
                use_element.text = "" # За замовчуванням порожній
                log_msg(logFile, "Додано відсутній елемент 'Use' до 'CategoryPurposeInfo'.")
            
            use = use_element.text if use_element.text is not None else ""
        else:
            # Якщо весь блок відсутній, створюємо його (малоймовірно, але надійно)
            category_purpose_info = etree.SubElement(parcel_info, "CategoryPurposeInfo")
            etree.SubElement(category_purpose_info, "Category").text = ""
            etree.SubElement(category_purpose_info, "Purpose").text = ""
            etree.SubElement(category_purpose_info, "Use").text = ""
            category, purpose, use = "", "", ""
        # --- Кінець змін ---

        # --- Початок змін: Забезпечення наявності OwnershipInfo ---
        ownership_info_element = parcel_info.find("OwnershipInfo")
        if ownership_info_element is None:
            # Якщо елемент OwnershipInfo відсутній, створюємо його і вставляємо в правильне місце
            ownership_info_element = etree.Element("OwnershipInfo")
            insert_element_in_order(parcel_info, ownership_info_element)
            log_msg(logFile, "Додано відсутній елемент 'OwnershipInfo' до 'ParcelInfo'.")

        code_element = ownership_info_element.find("Code")
        if code_element is None:
            # Якщо елемент Code відсутній, створюємо його
            code_element = etree.SubElement(ownership_info_element, "Code")
            code_element.text = "" # За замовчуванням порожній
            log_msg(logFile, "Додано відсутній елемент 'Code' до 'OwnershipInfo'.")
        
        code = code_element.text if code_element.text is not None else ""
        # --- Кінець змін ---

        # --- Початок змін: Забезпечення наявності Proprietors ---
        proprietors_element = parcel_info.find("Proprietors")
        if proprietors_element is None:
            proprietors_element = etree.Element("Proprietors")
            insert_element_in_order(parcel_info, proprietors_element)
            log_msg(logFile, "Додано відсутній елемент 'Proprietors' до 'ParcelInfo'.")
        # --- Кінець змін ---

        # Геометрія
        externals_element = metric_info.find(".//Externals")
        if externals_element is None:
            log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Для ділянки '{parcel_id}' відсутній обов'язковий розділ 'Externals'. Створено порожній об'єкт.")
            external_coords = []
        else:
            externals_lines = externals_element.find(".//Boundary/Lines")
            external_coords = self.lines_to_coords(externals_lines) if externals_lines is not None else []

        internals_lines = metric_info.find(".//Internals/Boundary/Lines")
        internal_coords = self.lines_to_coords(internals_lines) if internals_lines is not None else []

        polygon = self._coord_to_polygon(external_coords)
        if internal_coords:
            polygon.addInteriorRing(self._coord_to_polygon(internal_coords).exteriorRing())

        # Створення фічі
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry(polygon))
        feature.setAttributes([
            parcel_id, description, float(area_size) if area_size else None,
            area_unit, area_method, region, settlement, district,
            parcel_location, street_type, street_name, building, block,
            additional_info, category, purpose, use, code
        ])
        provider.addFeature(feature)

        # Додавання шару до проєкту та групи
        QgsProject.instance().addMapLayer(layer, False)
        layer_node = self.group.addLayer(layer)
        self.xml_ua_layers.added_layers.append(layer_node)
        self.xml_ua_layers.last_to_first(self.group)

        return layer