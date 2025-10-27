# -*- coding: utf-8 -*-
# new_xml.py

import os
import math
import copy
import uuid
from datetime import datetime
from lxml import etree

from qgis.core import QgsWkbTypes, QgsProject, QgsFeature
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from .common import logFile, log_msg, size, geometry_to_string, xml_template

class NewXmlCreator:
    """
    Клас, що інкапсулює логіку створення нового XML-файлу з шаблону
    на основі виділеного полігону в QGIS.
    """
    def __init__(self, iface, plugin_instance):
        self.iface = iface
        self.plugin = plugin_instance
        self.new_xml_path = ""

    def execute(self, geometry=None, template_path=None):
        """Основний метод для запуску процесу створення файлу."""
        base_template = template_path or xml_template
        #log_msg(logFile, f"Запуск створення нового XML-файлу. Шаблон: {os.path.basename(base_template)}")

        if not self.plugin.dockwidget:
            self.plugin.show_dockwidget()

        if geometry:
            # Якщо геометрія передана, створюємо фіктивну фічу
            selected_feature = QgsFeature()
            selected_feature.setGeometry(geometry)
        else:
            selected_feature = self.get_selection()
            if not selected_feature:
                return

        tree = self.set_intro_metric(selected_feature, selected_feature.geometry(), base_template)
        if not tree:
            return

        # Зберігаємо дерево з попередньою метрикою
        self.new_xml_path = self.save_tree_with_intro_metric(tree)
        if not self.new_xml_path:
            #log_msg(logFile, "Не збережено дерево з попередньою метрикою.")
            return

        # # Додаємо повну метрику (угіддя, обмеження тощо)
        # self.set_tree_full_metric(tree)

        # Передаємо фінальне дерево у док-віджет для відкриття
        self.plugin.dockwidget.process_action_new(self.new_xml_path, tree)

    def get_selection(self, layer=None):
        """
        Перевіряє, чи вибрано один геометричний об'єкт типу полігон або мультиполігон.
        """
        #log_msg(logFile)
        layers = [layer] if layer else QgsProject.instance().mapLayers().values()
        selected_features = []
        for layer in layers:
            if layer.type() == layer.VectorLayer:
                selected_features.extend(layer.selectedFeatures())

        if not selected_features:
            QMessageBox.warning(None, "Помилка", "Виділіть полігон меж земельної ділянки.")
            return None

        if len(selected_features) > 1:
            QMessageBox.warning(None, "Помилка", "Треба вибрати лише один полігон.")
            return None

        selected_feature = selected_features[0]
        geometry_type = selected_feature.geometry().wkbType()
        if geometry_type not in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
            QMessageBox.warning(None, "Помилка", "Межі земельної ділянки повинні бути полігоном або мультиполігоном.")
            return None

        #log_msg(logFile, f"Вибраний об'єкт: {size(selected_feature)} B\n" + geometry_to_string(selected_feature.geometry()))
        return selected_feature

    def set_intro_metric(self, selected_feature, geometry, template_file):
        """
        Створює XML-дерево на основі шаблону, додаючи точки та лінії з вибраного об'єкта.
        """
        #log_msg(logFile, f"Отриманий об'єкт: {size(selected_feature)} B")

        geometry = selected_feature.geometry()
        geometry_type = geometry.wkbType()

        points_list = []
        internals_points_list = []
        if geometry_type == QgsWkbTypes.Polygon:
            points_list.append(geometry.asPolygon()[0])
        elif geometry_type == QgsWkbTypes.MultiPolygon:
            for polygon in geometry.asMultiPolygon():
                points_list.append(polygon[0])
                for internal_ring in polygon[1:]:
                    internals_points_list.append(internal_ring)

        if not os.path.exists(template_file):
            QMessageBox.critical(None, "Помилка", f"Файл шаблону {template_file} не знайдено.")
            return None

        tree = etree.parse(template_file)
        root = tree.getroot()

        # Встановлюємо поточну дату та новий GUID
        try:
            current_date_str = datetime.now().strftime("%Y-%m-%d")
            new_guid = str(uuid.uuid4()).upper()

            file_date_element = root.find(".//ServiceInfo/FileID/FileDate")
            if file_date_element is not None:
                file_date_element.text = current_date_str

            drafting_date_element = root.find(".//TechnicalDocumentationInfo/DraftingDate")
            if drafting_date_element is not None:
                drafting_date_element.text = current_date_str

            file_guid_element = root.find(".//ServiceInfo/FileID/FileGUID")
            if file_guid_element is not None:
                file_guid_element.text = new_guid
            
            #log_msg(logFile, f"Встановлено дату: {current_date_str} та GUID: {new_guid}")
        except Exception as e:
            log_msg(logFile, f"Помилка при встановленні дати або GUID: {e}")

        # Обчислюємо площу та оновлюємо відповідний елемент у дереві
        try:
            area_m2 = geometry.area()
            area_ha = area_m2 / 10000.0
            area_str = f"{area_ha:.4f}"

            size_element = root.find(".//ParcelMetricInfo/Area/Size")
            if size_element is not None:
                size_element.text = area_str
                #log_msg(logFile, f"Встановлено площу ділянки: {area_str} га.")
            else:
                log_msg(logFile, "Елемент '.../ParcelMetricInfo/Area/Size' не знайдено у шаблоні.")
        except Exception as e:
            log_msg(logFile, f"Помилка при обчисленні або встановленні площі: {e}")

        point_info = root.find(".//InfoPart/MetricInfo/PointInfo")
        if point_info is not None:
            for point in point_info.findall("Point"):
                point_info.remove(point)

        uidp_counter = 1
        all_points_to_add = points_list + internals_points_list
        for points in all_points_to_add:
            points_without_last = points[:-1] if len(points) > 1 and points[0] == points[-1] else points
            for point in points_without_last:
                point_element = etree.SubElement(point_info, "Point")
                etree.SubElement(point_element, "UIDP").text = str(uidp_counter)
                etree.SubElement(point_element, "PN").text = str(uidp_counter)
                # --- Початок змін: Виправлення структури DeterminationMethod ---
                det_method_element = etree.SubElement(point_element, "DeterminationMethod")
                etree.SubElement(det_method_element, "GPS") # Створюємо дочірній елемент <GPS/>
                # --- Кінець змін ---
                etree.SubElement(point_element, "X").text = f"{point.y():.3f}"
                etree.SubElement(point_element, "Y").text = f"{point.x():.3f}"
                etree.SubElement(point_element, "H").text = "0.00"
                etree.SubElement(point_element, "MX").text = "0.05"
                etree.SubElement(point_element, "MY").text = "0.05"
                etree.SubElement(point_element, "MH").text = "0.05"
                etree.SubElement(point_element, "Description").text = ""
                uidp_counter += 1

        polyline_info = root.find(".//InfoPart/MetricInfo/Polyline")
        if polyline_info is not None:
            for pl in polyline_info.findall("PL"):
                polyline_info.remove(pl)

        ulid_counter = 1
        point_offset = 0
        for points in all_points_to_add:
            points_without_last = points[:-1] if len(points) > 1 and points[0] == points[-1] else points
            num_points = len(points_without_last)
            for i in range(num_points):
                start_point_idx = i
                end_point_idx = (i + 1) % num_points

                start_point = points_without_last[start_point_idx]
                end_point = points_without_last[end_point_idx]
                length = math.sqrt((end_point.x() - start_point.x())**2 + (end_point.y() - start_point.y())**2)

                pl_element = etree.SubElement(polyline_info, "PL")
                etree.SubElement(pl_element, "ULID").text = str(ulid_counter)
                points_element = etree.SubElement(pl_element, "Points")
                etree.SubElement(points_element, "P").text = str(point_offset + start_point_idx + 1)
                etree.SubElement(points_element, "P").text = str(point_offset + end_point_idx + 1)
                etree.SubElement(pl_element, "Length").text = f"{length:.2f}"
                ulid_counter += 1
            point_offset += num_points

        def find_or_create_path(root, path_parts):
            current = root
            for part in path_parts:
                found = current.find(part)
                if found is None:
                    found = etree.SubElement(current, part)
                current = found
            return current

        def add_boundary_lines(points_list, parent_element, is_internal=False):
            boundary_parent = parent_element
            if is_internal:
                internals_element = find_or_create_path(parent_element, ["Internals"])
                boundary_parent = internals_element

            boundary_element = find_or_create_path(boundary_parent, ["Boundary"])
            lines_element = find_or_create_path(boundary_element, ["Lines"])

            # Очищаємо існуючі лінії
            for line in lines_element.findall("Line"):
                lines_element.remove(line)

            # Використовуємо той самий лічильник ULID, що й для загального списку
            nonlocal ulid_counter
            for _ in points_list:
                points_without_last = _[:-1] if len(_) > 1 and _[0] == _[-1] else _
                for i in range(len(points_without_last)):
                    line_element = etree.SubElement(lines_element, "Line")
                    # Потрібно знайти правильний ULID з polyline_info
                    # Це спрощення, яке може бути неточним, якщо порядок не гарантований
                    etree.SubElement(line_element, "ULID").text = str(ulid_counter - len(points_without_last) + i)

            # --- Початок виправлення: Переміщення 'Closed' на правильний рівень ---
            # Елемент 'Closed' має бути дочірнім до 'Boundary', а не до 'Lines'
            closed_element = boundary_element.find("Closed")
            if closed_element is None:
                closed_element = etree.SubElement(boundary_element, "Closed")
            closed_element.text = "true"
            # --- Кінець виправлення ---

        parcel_metric_info_path = [
            "InfoPart", "CadastralZoneInfo", "CadastralQuarters",
            "CadastralQuarterInfo", "Parcels", "ParcelInfo", "ParcelMetricInfo"
        ]
        parcel_metric_info_element = find_or_create_path(root, parcel_metric_info_path)
        externals_element = find_or_create_path(parcel_metric_info_element, ["Externals"])

        # --- Початок змін: Гарантуємо наявність ParcelID ---
        parcel_id_element = parcel_metric_info_element.find("ParcelID")
        if parcel_id_element is None:
            parcel_id_element = etree.Element("ParcelID")
            parcel_metric_info_element.insert(0, parcel_id_element) # Вставляємо на першу позицію
        # --- Кінець змін ---

        add_boundary_lines(points_list, externals_element)
        if internals_points_list:
            add_boundary_lines(internals_points_list, externals_element, is_internal=True)

        # --- Початок змін: Копіювання геометрії до CadastralZoneInfo та CadastralQuarterInfo ---
        parcel_externals_node = parcel_metric_info_element.find("Externals")
        if parcel_externals_node is not None:
            # Копіюємо в CadastralZoneInfo
            zone_info_element = root.find(".//InfoPart/CadastralZoneInfo")
            zone_number_element = root.find(".//InfoPart/CadastralZoneInfo/CadastralZoneNumber")
            if zone_info_element is not None and zone_number_element is not None:
                # Видаляємо старий Externals, якщо він є
                old_zone_externals = zone_info_element.find("Externals")
                if old_zone_externals is not None:
                    zone_info_element.remove(old_zone_externals)
                # Вставляємо новий Externals після CadastralZoneNumber
                zone_number_element.addnext(copy.deepcopy(parcel_externals_node))

            # Копіюємо в CadastralQuarterInfo
            quarter_info_element = root.find(".//InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo")
            regional_contacts_element = root.find(".//InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/RegionalContacts")
            if quarter_info_element is not None and regional_contacts_element is not None:
                # Видаляємо старий Externals, якщо він є
                old_quarter_externals = quarter_info_element.find("Externals")
                if old_quarter_externals is not None:
                    quarter_info_element.remove(old_quarter_externals)
                # Вставляємо новий Externals після RegionalContacts
                regional_contacts_element.addnext(copy.deepcopy(parcel_externals_node))

        # --- Кінець змін ---

        #log_msg(logFile, f"tree: {size(tree)} B")
        return tree

    def save_tree_with_intro_metric(self, tree):
        """Зберігає дерево з попередньою метрикою, запитуючи шлях у користувача."""
        #log_msg(logFile, f"tree before saving: {size(tree)} B")

        save_path, _ = QFileDialog.getSaveFileName(None, "Зберегти новий XML файл", "", "XML файли (*.xml)")
        if not save_path:
            #log_msg(logFile, "Шлях для збереження не вибрано.")
            return None

        try:
            tree.write(save_path, encoding="utf-8", xml_declaration=True)
            #log_msg(logFile, f"Новий XML файл збережено за адресою: {save_path}")
            return save_path
        except Exception as e:
            QMessageBox.critical(None, "Помилка збереження", f"Не вдалося зберегти файл: {e}")
            return None

    def set_tree_full_metric(self, tree):
        """Додає до дерева повну метрику (угіддя, обмеження тощо)."""
        #log_msg(logFile, f"tree: {size(tree)} B")
        self.add_land_parcels(tree)
        return tree

    def add_land_parcels(self, tree):
        """Додає до дерева угіддя."""
        #log_msg(logFile, f"tree: {size(tree)} B")

        source_element = tree.find(".//ParcelMetricInfo/Externals")
        if source_element is None:
            #log_msg(logFile, "Не знайдено елемент ParcelMetricInfo/Externals.")
            return tree

        parent_element = tree.find(".//ParcelInfo")
        if parent_element is None:
            #log_msg(logFile, "Не знайдено батьківський елемент для LandsParcel.")
            return tree

        lands_parcel_element = etree.SubElement(parent_element, "LandsParcel")
        land_parcel_info_element = etree.SubElement(lands_parcel_element, "LandParcelInfo")
        metric_info_element = etree.SubElement(land_parcel_info_element, "MetricInfo")
        externals_element = etree.SubElement(metric_info_element, "Externals")

        for child in source_element:
            externals_element.append(copy.deepcopy(child))

        #log_msg(logFile, f"tree: {size(tree)} B")
        return tree

    # Наступні методи є заглушками і потребують реалізації
    def get_parcel_polygon(self):
        """
        Gets the parcel polygon from the selected feature.
        """
        #log_msg(logFile)
        
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

    def wait_for_polygon_selection(self):
        """
        Waits for the user to select a polygon on the QGIS canvas.
        """
        # TODO: Implement a proper way to wait for a selection event.
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
        #log_msg(logFile)
        # TODO: Implement the logic to add the land use polygon to the XML.
        parcel_info_element = tree.find(".//CadastralQuarterInfo/Parcels/ParcelInfo")
        if parcel_info_element is None:
            #log_msg(logFile, "Не знайдено елемент ParcelInfo.")
            QMessageBox.warning(None, "Помилка", "Не знайдено елемент ParcelInfo.")
            return

        land_use_element = etree.SubElement(parcel_info_element, "LandUse")
        etree.SubElement(land_use_element, "Type").text = "Unknown"

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
            #log_msg(logFile, "Не знайдено елемент ParcelMetricInfo/Externals.")
            QMessageBox.warning(None, "Помилка", "Не знайдено елемент ParcelMetricInfo/Externals.")
            return tree

        parent_element = tree.find(
            ".//CadastralQuarterInfo/Parcels/ParcelInfo"
        )
        if parent_element is None:
            #log_msg(logFile, "Не знайдено батьківський елемент для LandsParcel.")
            QMessageBox.warning(None, "Помилка", "Не знайдено батьківський елемент для LandsParcel.")
            return tree

        lands_parcel_element = etree.SubElement(parent_element, "LandsParcel")
        land_parcel_info_element = etree.SubElement(lands_parcel_element, "LandParcelInfo")
        metric_info_element = etree.SubElement(land_parcel_info_element, "MetricInfo")
        externals_element = etree.SubElement(metric_info_element, "Externals")

        for child in source_element:
            externals_element.append(copy.deepcopy(child))

        #log_msg(logFile, f"tree: {size(tree)} B")

        return tree