# -*- coding: utf-8 -*-
# topology.py
"""
Модуль для обробки та унікалізації геометричних даних в XML.
"""
import math
from lxml import etree as etree
from qgis.core import QgsGeometry, QgsPolygon, QgsMultiPolygon, QgsWkbTypes, QgsPointXY

from .common import log_msg, logFile, insert_element_in_order

class GeometryProcessor:
    """
    Клас для обробки геометрії: унікалізації вузлів та поліліній
    при додаванні нових геометричних об'єктів до XML.
    """
    def __init__(self, tree):
        self.tree = tree
        self.root = self.tree.getroot()
        self.points = self._get_all_points()
        self.polylines = self._get_all_polylines()
        self.max_uidp = self._get_max_id('.//PointInfo/Point', 'UIDP')
        self.max_pn = self._get_max_id('.//PointInfo/Point', 'PN')
        self.max_ulid = self._get_max_id('.//Polyline/PL', 'ULID')
        self.tolerance = 0.10  # 10 см
        self.point_info = self.root.find(".//PointInfo")
        self.polyline_info = self.root.find(".//Polyline")
        self.existing_points = self._get_existing_points()

    def _get_max_id(self, xpath, tag):
        """Знаходить максимальний числовий ID для UIDP або ULID."""
        max_id = 0
        for elem in self.root.xpath(xpath):
            id_text = elem.findtext(tag)
            if id_text and id_text.isdigit():
                max_id = max(max_id, int(id_text))
        return max_id

    def _get_existing_points(self):
        """Створює словник існуючих точок для швидкого пошуку за координатами."""
        points = {}
        for p_elem in self.root.findall('.//PointInfo/Point'):
            uidp = p_elem.findtext('UIDP')
            try:
                y = float(p_elem.findtext('X'))
                x = float(p_elem.findtext('Y'))
                coord_tuple = (round(y, 3), round(x, 3))
                points[coord_tuple] = uidp
            except (ValueError, TypeError):
                continue
        return points

    def _get_all_points(self):
        """Збирає всі існуючі точки з XML у словник."""
        points_dict = {}
        for p_elem in self.root.findall('.//PointInfo/Point'):
            uidp = p_elem.findtext('UIDP')
            try:
                # Пам'ятаємо, що в XML X та Y поміняні місцями відносно QGIS
                y = float(p_elem.findtext('X'))
                x = float(p_elem.findtext('Y'))
                if uidp:
                    points_dict[uidp] = {'x': x, 'y': y, 'elem': p_elem}
            except (ValueError, TypeError):
                continue
        return points_dict

    def _get_all_polylines(self):
        """Збирає всі існуючі полілінії з XML у словник."""
        polylines_dict = {}
        for pl_elem in self.root.findall('.//Polyline/PL'):
            ulid = pl_elem.findtext('ULID')
            points = [p.text for p in pl_elem.findall('Points/P')]
            if ulid and points:
                # Зберігаємо відсортований набір точок для порівняння
                polylines_dict[ulid] = {'points': points, 'elem': pl_elem}
        return polylines_dict

    def _get_or_create_point(self, qgs_point):
        """
        Перевіряє, чи існує точка з такими координатами.
        Якщо так, повертає її UIDP. Якщо ні, створює нову точку та повертає її UIDP.
        """
        # --- Початок змін: Пошук існуючої точки в межах допуску ---
        # Пам'ятаємо, що в QGIS x -> Y в XML, y -> X в XML
        new_x, new_y = qgs_point.x(), qgs_point.y()

        for uidp, point_data in self.points.items():
            # Координати з XML вже відповідають QGIS (x, y)
            existing_x, existing_y = point_data['x'], point_data['y']
            distance = math.sqrt((new_x - existing_x)**2 + (new_y - existing_y)**2)
            
            if distance < self.tolerance:
                log_msg(logFile, f"Знайдено існуючу точку UIDP: {uidp} в межах допуску {self.tolerance}м. Використовуємо її.")
                return uidp
        # --- Кінець змін ---
        
        if self.point_info is None:
            metric_info = self.root.find(".//MetricInfo")
            self.point_info = etree.SubElement(metric_info, "PointInfo")

        self.max_uidp += 1
        self.max_pn += 1
        new_point_element = etree.Element("Point")
        etree.SubElement(new_point_element, "UIDP").text = str(self.max_uidp)
        etree.SubElement(new_point_element, "PN").text = str(self.max_pn)
        det_method = etree.SubElement(new_point_element, "DeterminationMethod")
        etree.SubElement(det_method, "Survey")
        etree.SubElement(new_point_element, "X").text = f"{qgs_point.y():.3f}"
        etree.SubElement(new_point_element, "Y").text = f"{qgs_point.x():.3f}"

        self.point_info.append(new_point_element)
        # Оновлюємо кеш існуючих точок
        self.points[str(self.max_uidp)] = {'x': qgs_point.x(), 'y': qgs_point.y(), 'elem': new_point_element}
        log_msg(logFile, f"Створено нову точку з UIDP: {self.max_uidp}")
        return str(self.max_uidp)

    def find_point_uidp(self, qgs_point: QgsPointXY):
        """
        Знаходить UIDP існуючої точки в межах допуску. Не створює нову.
        """
        new_x, new_y = qgs_point.x(), qgs_point.y()

        for uidp, point_data in self.points.items():
            existing_x, existing_y = point_data['x'], point_data['y']
            distance = math.sqrt((new_x - existing_x)**2 + (new_y - existing_y)**2)
            
            if distance < self.tolerance:
                return uidp
        return None


    def _create_polyline(self, uidp1, uidp2, p1, p2):
        """Створює новий елемент PL (полілінія) між двома точками."""
        # --- Початок змін: Перевірка на існування лінії ---
        # Створюємо множину з UIDP для порівняння незалежно від порядку
        segment_points_set = frozenset([uidp1, uidp2])
        for ulid, polyline_data in self.polylines.items():
            if frozenset(polyline_data['points']) == segment_points_set:
                log_msg(logFile, f"Знайдено існуючу лінію ULID: {ulid}. Використовуємо її.")
                return ulid
        # --- Кінець змін ---

        if self.polyline_info is None:
            metric_info = self.root.find(".//MetricInfo")
            self.polyline_info = etree.SubElement(metric_info, "Polyline")

        self.max_ulid += 1
        new_ulid = str(self.max_ulid)
        log_msg(logFile, f"Створено нову лінію з ULID: {new_ulid} між точками {uidp1} та {uidp2}.")
        pl_element = etree.Element("PL")
        etree.SubElement(pl_element, "ULID").text = new_ulid
        points_element = etree.SubElement(pl_element, "Points")
        etree.SubElement(points_element, "P").text = uidp1
        etree.SubElement(points_element, "P").text = uidp2
        
        length = math.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2) # p1, p2 - це QgsPointXY
        etree.SubElement(pl_element, "Length").text = f"{length:.2f}"

        self.polyline_info.append(pl_element)
        # Оновлюємо кеш існуючих поліліній
        self.polylines[new_ulid] = {'points': [uidp1, uidp2], 'elem': pl_element}

        return new_ulid

    def process_new_geometry(self, qgis_geom: QgsGeometry):
        """
        Обробляє нову геометрію, унікалізує вузли та полілінії,
        та повертає структуру для вставки в XML.
        """
        object_shapes = []
        geom_part = qgis_geom.constGet()
        if qgis_geom.isNull() or not isinstance(geom_part, (QgsPolygon, QgsMultiPolygon)):
            return None, None, None, None

        new_points_to_add = []
        new_polylines_to_add = []

        externals = etree.Element("Externals")
        
        polygon = geom_part if isinstance(geom_part, QgsPolygon) else geom_part.geometryN(0)

        # Обробляємо зовнішній контур
        exterior_ring = polygon.exteriorRing()
        if exterior_ring:
            boundary_ulids, processed_points, processed_polylines = self._process_ring(exterior_ring)
            new_points_to_add.extend(processed_points)
            new_polylines_to_add.extend(processed_polylines)
            
            boundary = etree.SubElement(externals, "Boundary")
            # --- Початок виправлення: Переміщення 'Closed' на правильний рівень ---
            lines = etree.SubElement(boundary, "Lines")
            for ulid in boundary_ulids:
                line_elem = etree.SubElement(lines, "Line")
                etree.SubElement(line_elem, "ULID").text = ulid
            etree.SubElement(boundary, "Closed").text = "true"
            # --- Кінець виправлення ---
            object_shapes.append(self._get_polyline_object_shape(lines))

        # --- Початок змін: Обробка внутрішніх контурів (отворів) ---
        internals = None
        if polygon.numInteriorRings() > 0:
            internals = etree.Element("Internals")
            for i in range(polygon.numInteriorRings()):
                interior_ring = polygon.interiorRing(i)
                if interior_ring:
                    boundary_ulids, processed_points, processed_polylines = self._process_ring(interior_ring)
                    new_points_to_add.extend(processed_points)
                    new_polylines_to_add.extend(processed_polylines)

                    boundary = etree.SubElement(internals, "Boundary")
                    # --- Початок виправлення: Переміщення 'Closed' на правильний рівень ---
                    lines = etree.SubElement(boundary, "Lines")
                    for ulid in boundary_ulids:
                        line_elem = etree.SubElement(lines, "Line")
                        etree.SubElement(line_elem, "ULID").text = ulid
                    etree.SubElement(boundary, "Closed").text = "true"
                    object_shapes.append(self._get_polyline_object_shape(lines))
                    # --- Кінець виправлення ---

        # --- Початок змін: Додавання нових елементів до основного дерева XML та об'єднання object_shape ---
        # Додаємо унікальні нові елементи до головного дерева XML.
        # Це потрібно робити тут, щоб гарантувати, що всі точки та лінії
        # (включаючи ті, що з отворів) будуть доступні при подальшій обробці.
        point_info_container = self.root.find('.//PointInfo')
        if point_info_container is not None:
            # Використовуємо extend для додавання всіх елементів списку
            point_info_container.extend(new_points_to_add)

        polyline_container = self.root.find('.//Polyline')
        if polyline_container is not None:
            polyline_container.extend(new_polylines_to_add)

        # --- Кінець змін ---
        # Додаємо Internals до Externals, щоб повернути єдиний блок для вставки
        if internals is not None:
            externals.append(internals)

        # Об'єднуємо object_shape для всіх контурів через '|'
        final_object_shape = "|".join(filter(None, object_shapes))
        return externals, new_points_to_add, new_polylines_to_add, final_object_shape

    def _process_ring(self, ring):
        """Обробляє один контур (QgsLineString)."""
        newly_created_points = []
        newly_created_polylines = []
        boundary_ulids = []

        points_in_ring = ring.points()
        if len(points_in_ring) > 1 and points_in_ring[0] == points_in_ring[-1]:
            points_in_ring = points_in_ring[:-1]

        # 1. Обробка вузлів
        ring_uidps = []
        for qgis_point in points_in_ring:
            found_existing = False
            for uidp, data in self.points.items():
                dist = math.sqrt((qgis_point.x() - data['x'])**2 + (qgis_point.y() - data['y'])**2)
                if dist < self.tolerance:
                    ring_uidps.append(uidp)
                    found_existing = True
                    break
            if not found_existing:
                self.max_uidp += 1
                new_uidp = str(self.max_uidp)
                ring_uidps.append(new_uidp)
                
                p_elem = etree.Element("Point")
                etree.SubElement(p_elem, "UIDP").text = new_uidp
                etree.SubElement(p_elem, "PN").text = new_uidp
                det_method = etree.SubElement(p_elem, "DeterminationMethod")
                etree.SubElement(det_method, "GPS")
                etree.SubElement(p_elem, "X").text = f"{qgis_point.y():.3f}" # Y -> X
                etree.SubElement(p_elem, "Y").text = f"{qgis_point.x():.3f}" # X -> Y
                etree.SubElement(p_elem, "H").text = "0.00"
                etree.SubElement(p_elem, "MX").text = "0.05"
                etree.SubElement(p_elem, "MY").text = "0.05"
                etree.SubElement(p_elem, "MH").text = "0.05"
                etree.SubElement(p_elem, "Description").text = ""
                newly_created_points.append(p_elem)
                self.points[new_uidp] = {'x': qgis_point.x(), 'y': qgis_point.y(), 'elem': p_elem}

        # 2. Обробка поліліній (сегментів)
        for i in range(len(ring_uidps)):
            p1_uidp = ring_uidps[i]
            p2_uidp = ring_uidps[(i + 1) % len(ring_uidps)]
            current_segment_points = {p1_uidp, p2_uidp}

            # Перевірка на існування полілінії
            found_existing_pl = False
            for ulid, data in self.polylines.items():
                if frozenset(data['points']) == current_segment_points:
                    boundary_ulids.append(ulid)
                    found_existing_pl = True
                    break
            
            if not found_existing_pl:
                self.max_ulid += 1
                new_ulid = str(self.max_ulid)
                boundary_ulids.append(new_ulid)

                pl_elem = etree.Element("PL")
                etree.SubElement(pl_elem, "ULID").text = new_ulid
                points_container = etree.SubElement(pl_elem, "Points")
                etree.SubElement(points_container, "P").text = p1_uidp
                etree.SubElement(points_container, "P").text = p2_uidp
                
                p1_coords = self.points[p1_uidp]
                p2_coords = self.points[p2_uidp]
                length = math.sqrt((p2_coords['x'] - p1_coords['x'])**2 + (p2_coords['y'] - p1_coords['y'])**2)
                etree.SubElement(pl_elem, "Length").text = f"{length:.2f}"
                
                newly_created_polylines.append(pl_elem)
                self.polylines[new_ulid] = {'points': [p1_uidp, p2_uidp], 'elem': pl_elem}

        return boundary_ulids, newly_created_points, newly_created_polylines

    def process_adjacent_unit_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію суміжника, оновлює PointInfo, Polyline та додає AdjacentUnitInfo.
        """
        # --- Початок змін: Логування стану дерева ---
        adj_units_before = self.root.find(".//AdjacentUnits")
        if adj_units_before is None:
            log_msg(logFile, "(початок): Розділ 'AdjacentUnits' ВІДСУТНІЙ.")
        else:
            count = len(adj_units_before.findall("AdjacentUnitInfo"))
            log_msg(logFile, f"(початок): Розділ 'AdjacentUnits' ІСНУЄ. Кількість суміжників: {count}.")
        # --- Кінець змін ---
        log_msg(logFile)
        if geometry.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            raise ValueError("Геометрія суміжника повинна бути полілінією.")

        if geometry.type() == QgsWkbTypes.MultiLineString:
            # Беремо першу частину мультилінії
            polyline = geometry.asMultiPolyline()[0]
        else:
            polyline = geometry.asPolyline()
            
        # polyline тепер є списком QgsPointXY
        # --- Початок змін: Формування object_shape ---
        line_ulids = []
        point_uidps = []
        # 1. Створюємо точки та лінії
        for i in range(len(polyline) - 1):
            p1, p2 = polyline[i], polyline[i+1]
            uidp1 = self._get_or_create_point(p1)
            uidp2 = self._get_or_create_point(p2)
            # Збираємо послідовність UIDP для object_shape
            if i == 0:
                point_uidps.append(uidp1)
            point_uidps.append(uidp2)
            ulid = self._create_polyline(uidp1, uidp2, p1, p2)
            line_ulids.append(ulid)

        # Формуємо рядок object_shape
        object_shape = "-".join(point_uidps)
        # --- Кінець змін ---

        # --- Початок змін: Перевірка на дублювання суміжника ---
        # Перевіряємо, чи вже існує суміжник з таким же набором ліній
        for adj_unit in self.root.findall(".//AdjacentUnitInfo"):
            existing_ulids = {line.findtext("ULID") for line in adj_unit.findall(".//AdjacentBoundary/Lines/Line")}
            if set(line_ulids) == existing_ulids:
                # log_msg(logFile, f"Суміжник з таким набором ліній ({line_ulids}) вже існує. Новий не буде додано.")
                return  # Виходимо, щоб не створювати дублікат
        # --- Кінець змін ---

        # 2. Знаходимо або створюємо контейнер <AdjacentUnits>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        adjacent_units_container = parcel_info.find("AdjacentUnits")
        if adjacent_units_container is None:
            # --- Початок змін: Створення та вставка відсутнього розділу --- #
            log_msg(logFile, "Розділ 'AdjacentUnits' відсутній. Створюємо новий.") #
            adjacent_units_container = etree.Element("AdjacentUnits") # Створюємо новий елемент #
            # Вставляємо його у правильне місце згідно зі схемою #
            # --- Початок змін: Логування стану дерева ---
            adj_units_after_creation = self.root.find(".//AdjacentUnits")
            if adj_units_after_creation is None:
                log_msg(logFile, "(після створення контейнера): Розділ 'AdjacentUnits' все ще ВІДСУТНІЙ.")
            else:
                log_msg(logFile, "(після створення контейнера): Розділ 'AdjacentUnits' тепер ІСНУЄ.")
            # --- Кінець змін ---
            insert_element_in_order(parcel_info, adjacent_units_container) #
            # --- Кінець змін --- #

        # 3. Створюємо новий <AdjacentUnitInfo>
        adj_unit_info = etree.SubElement(adjacent_units_container, "AdjacentUnitInfo")

        # 4. Створюємо <AdjacentBoundary>
        adj_boundary = etree.SubElement(adj_unit_info, "AdjacentBoundary")
        lines = etree.SubElement(adj_boundary, "Lines")
        for ulid in line_ulids:
            line_el = etree.SubElement(lines, "Line")
            etree.SubElement(line_el, "ULID").text = ulid
        
        # Додаємо обов'язковий елемент <Closed> зі значенням 'false'
        etree.SubElement(adj_boundary, "Closed").text = "false"

        # Додаємо порожній елемент Proprietor, щоб він з'явився в дереві
        etree.SubElement(adj_unit_info, "Proprietor")

        # --- Початок змін: Логування стану дерева ---
        if adjacent_units_container is not None:
            count = len(adjacent_units_container.findall("AdjacentUnitInfo"))
            log_msg(logFile, f"(після додавання елемента): Розділ 'AdjacentUnits' ІСНУЄ. Кількість суміжників: {count}.")
        else:
            log_msg(logFile, "(після додавання елемента): Розділ 'AdjacentUnits' несподівано став ВІДСУТНІМ.")
        # --- Кінець змін ---
        log_msg(logFile, f"Додано нового суміжника: {object_shape}.")

    def delete_adjacent_by_shape(self, object_shape_to_delete: str):
        """
        Видаляє суміжника з XML-дерева за його object_shape.
        """
        points_to_check = object_shape_to_delete.split('-')
        if not points_to_check:
            return

        adjacent_units_container = self.root.find(".//AdjacentUnits")
        if adjacent_units_container is None:
            return

        element_to_delete = None
        for adj_unit in adjacent_units_container.findall("AdjacentUnitInfo"):
            boundary_lines = adj_unit.findall(".//AdjacentBoundary/Lines/Line")
            if not boundary_lines:
                continue

            # Відновлюємо object_shape для поточного суміжника
            current_shape_points = set()
            for line in boundary_lines:
                ulid = line.findtext("ULID")
                if ulid in self.polylines:
                    current_shape_points.update(self.polylines[ulid]['points'])
            
            # Порівнюємо набори точок, щоб бути незалежними від порядку
            if set(points_to_check) == current_shape_points:
                element_to_delete = adj_unit
                break
        
        if element_to_delete is not None:
            adjacent_units_container.remove(element_to_delete)
            log_msg(logFile, f"Суміжника {object_shape_to_delete} було видалено з XML.")
            # Якщо після видалення контейнер суміжників став порожнім, видаляємо і його
            if not adjacent_units_container.findall("AdjacentUnitInfo"):
                adjacent_units_container.getparent().remove(adjacent_units_container)
                log_msg(logFile, "Розділ 'AdjacentUnits' став порожнім і був видалений.")

    def delete_adjacents_not_in_set(self, remaining_shapes: set):
        """
        Видаляє з XML-дерева всі суміжники, object_shape яких
        не присутній у наданому наборі `remaining_shapes`.
        """
        adjacent_units_container = self.root.find(".//AdjacentUnits")
        if adjacent_units_container is None:
            return []

        elements_to_delete = []

        for adj_unit in adjacent_units_container.findall("AdjacentUnitInfo"):
            boundary_lines = adj_unit.findall(".//AdjacentBoundary/Lines/Line")
            if not boundary_lines:
                continue

            # Відновлюємо object_shape для поточного суміжника
            current_shape_points = []
            
            # --- Початок змін: Надійне відновлення послідовності точок з логуванням ---
            segments = []
            for line in boundary_lines:
                ulid = line.findtext("ULID")
                if ulid in self.polylines:
                    segments.append(self.polylines[ulid]['points'])
            
            if segments: # noqa
                # Починаємо з першого сегмента, якщо він є
                if segments:
                    current_shape_points.extend(segments.pop(0))
                    # Продовжуємо, поки є сегменти для з'єднання
                    while segments:
                        last_point = current_shape_points[-1]
                        # Шукаємо сегмент, який приєднується до кінця ланцюжка
                        found_next = False
                        for i, seg in enumerate(segments):
                            if seg[0] == last_point:
                                current_shape_points.append(seg[1])
                                segments.pop(i)
                                found_next = True
                                break
                            elif seg[1] == last_point:
                                current_shape_points.append(seg[0])
                                segments.pop(i)
                                found_next = True
                                break
                        if not found_next:
                            # Якщо не знайдено приєднаного сегмента, ланцюжок розірвано
                            log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Ланцюжок суміжника розірвано. Залишилось {len(segments)} нез'єднаних сегментів.")
                            break
            # --- Кінець змін ---
            
            current_shape = "-".join(current_shape_points)

            if current_shape not in remaining_shapes:
                elements_to_delete.append(adj_unit)

        for element in elements_to_delete:
            adjacent_units_container.remove(element)
        
        # Повертаємо список видалених елементів для подальшої обробки
        return elements_to_delete
    
    def _get_polyline_object_shape(self, lines_container):
        """
        Відновлює та повертає рядкове представлення геометрії (object_shape)
        з XML-контейнера <Lines>.

        Цей метод є критично важливим для ідентифікації та порівняння геометрії
        суміжників та ділянки. Він збирає окремі сегменти (лінії) з XML та
        відновлює їхню правильну послідовність, щоб сформувати єдиний ланцюжок точок.

        Args:
            lines_container (lxml.etree._Element): XML-елемент, що містить
                список елементів <Line> (наприклад, <AdjacentBoundary>/<Lines>
                або <ParcelMetricInfo>/<Externals>/<Boundary>/<Lines>).

        Returns:
            str: Рядок, що представляє послідовність унікальних ідентифікаторів
                 точок (UIDP), з'єднаних дефісом. Наприклад: "12-1-8-6-11".
                 Повертає порожній рядок, якщо геометрію неможливо відновити.

        Алгоритм роботи:
        1.  **Збір сегментів**: Метод ітерує по всіх елементах <Line> всередині
            `lines_container`. Для кожного <Line> він знаходить ULID та,
            використовуючи кеш `self.polylines`, отримує відповідну пару UIDP
            точок (сегмент). Усі знайдені сегменти збираються у список.
        2.  **Ініціалізація ланцюжка**: Береться перший сегмент зі списку, і його
            точки додаються до результуючого списку `shape_points`.
        3.  **З'єднання ланцюжка**: Метод в циклі шукає наступний сегмент, який
            можна приєднати до останньої точки поточного ланцюжка.
        4.  **Пошук з'єднання**: Для кожного сегмента, що залишився, перевіряється,
            чи одна з його точок збігається з останньою точкою в `shape_points`.
        5.  **Додавання точки**: Якщо з'єднання знайдено, "нова" точка сегмента
            додається в кінець `shape_points`, а сам сегмент видаляється зі списку
            кандидатів.
        6.  **Обробка розривів**: Якщо на якійсь ітерації не вдається знайти
            сегмент для приєднання, це означає, що ланцюжок розірвано. Процес
            зупиняється, і в лог виводиться попередження.
        7.  **Формування результату**: Всі зібрані UIDP з'єднуються в єдиний
            рядок через дефіс.
        """
        # --- Початок змін: Логування на вході ---
        if lines_container is None:
            log_msg(logFile, "На вхід подано порожній `lines_container`.")
            return ""
        
        parent_tag = lines_container.getparent().tag if lines_container.getparent() is not None else "N/A"
        ulids_in_container = [line.findtext('ULID') for line in lines_container.findall('Line') if line.findtext('ULID') is not None]
        log_msg(logFile, f"'{parent_tag}' ULIDs: {ulids_in_container}")
        # --- Кінець змін ---
        if lines_container is None:
            return ""
        segments = []
        for line in lines_container.findall('Line'):
            ulid = line.findtext('ULID')
            if ulid and ulid in self.polylines:
                segments.append(self.polylines[ulid]['points'])
        
        if not segments:
            return ""

        shape_points = []
        # --- Початок змін: Надійний алгоритм з'єднання невпорядкованих сегментів ---
        if segments:
            # 1. Починаємо ланцюжок з першого сегмента
            shape_points.extend(segments.pop(0))
            
            # 2. Продовжуємо, поки є сегменти для з'єднання
            while segments:
                start_point = shape_points[0]
                end_point = shape_points[-1]
                found_next = False

                # 3. Шукаємо сегмент, який можна приєднати
                for i, seg in enumerate(segments):
                    # Приєднати до кінця
                    if seg[0] == end_point:
                        shape_points.append(seg[1])
                        segments.pop(i)
                        found_next = True
                        break
                    elif seg[1] == end_point:
                        shape_points.append(seg[0])
                        segments.pop(i)
                        found_next = True
                        break
                    # Приєднати до початку
                    elif seg[0] == start_point:
                        shape_points.insert(0, seg[1])
                        segments.pop(i)
                        found_next = True
                        break
                    elif seg[1] == start_point:
                        shape_points.insert(0, seg[0])
                        segments.pop(i)
                        found_next = True
                        break

                if not found_next:
                    log_msg(logFile, f"ПОПЕРЕДЖЕННЯ: Ланцюжок суміжника розірвано. Залишилось {len(segments)} нез'єднаних сегментів.")
                    break  # Ланцюжок розірвано
        # --- Кінець змін ---
        # --- Початок змін: Логування на виході ---
        result = "-".join(shape_points)
        log_msg(logFile, f"object_shape: '{result}'")
        return result
        # --- Кінець змін ---

    def get_shape_from_qgis_feature(self, feature: 'QgsFeature'):
        """
        Відновлює object_shape для графічного об'єкта QGIS.
        """
        geom = feature.geometry()
        if geom.isNull() or geom.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            return ""

        if geom.type() == QgsWkbTypes.MultiLineString:
            polyline = geom.asMultiPolyline()[0]
        else:
            polyline = geom.asPolyline()

        shape_uidps = []
        for p in polyline:
            uidp = self.find_point_uidp(p)
            if uidp:
                shape_uidps.append(uidp)
            else:
                log_msg(logFile, f"Попередження: не знайдено UIDP для точки з координатами {p.x()}, {p.y()}")
        return "-".join(shape_uidps)

    def cleanup_geometry(self, deleted_adj_units):
        """
        Безпечно видаляє "осиротілі" лінії та точки згідно з уточненим алгоритмом.
        """
        log_msg(logFile, "--- Початок безпечного очищення геометрії ---")

        # 1. Створюємо список object_shape суміжників, що підлягають видаленню
        deleted_adj_shapes = [self._get_polyline_object_shape(adj.find('AdjacentBoundary/Lines')) for adj in deleted_adj_units]
        log_msg(logFile, f"1. Суміжники до видалення (object_shape): {deleted_adj_shapes}")

        # 2. Створюємо список object_shape суміжників, що залишаються
        remaining_adj_shapes = [self._get_polyline_object_shape(adj.find('AdjacentBoundary/Lines')) for adj in self.root.findall(".//AdjacentUnitInfo")]
        log_msg(logFile, f"2. Суміжники, що залишаються (object_shape): {remaining_adj_shapes}")

        # 3. Додаємо object_shape ділянки
        parcel_lines = self.root.find(".//ParcelMetricInfo/Externals/Boundary/Lines")
        parcel_shape = self._get_polyline_object_shape(parcel_lines)
        log_msg(logFile, f"3. Ділянка (object_shape): {parcel_shape}")

        # 4. Створюємо множину точок, які залишаються
        points_to_keep = set()
        for shape in remaining_adj_shapes + [parcel_shape]:
            if shape: points_to_keep.update(shape.split('-'))
        log_msg(logFile, f"4. Точки, що залишаються (UIDP): {sorted(list(points_to_keep))}")

        # 5. Створюємо множину точок, кандидатів на видалення
        points_candidates_for_deletion = set()
        for shape in deleted_adj_shapes:
            if shape: points_candidates_for_deletion.update(shape.split('-'))
        log_msg(logFile, f"5. Точки-кандидати на видалення (UIDP): {sorted(list(points_candidates_for_deletion))}")

        # 6. Фільтруємо множину точок на видалення
        final_points_to_delete = points_candidates_for_deletion - points_to_keep
        log_msg(logFile, f"6. Точки, що будуть видалені (UIDP): {sorted(list(final_points_to_delete))}")

        # 7. Створюємо множину ліній, кандидатів на видалення
        lines_candidates_for_deletion = set()
        for shape in deleted_adj_shapes:
            if shape:
                points = shape.split('-')
                for i in range(len(points) - 1):
                    lines_candidates_for_deletion.add(frozenset([points[i], points[i+1]]))
        log_msg(logFile, f"7. Лінії-кандидати на видалення: {[f'{p1}-{p2}' for p1, p2 in lines_candidates_for_deletion]}")

        # 8. Створюємо множину ліній, які залишаються
        lines_to_keep = set()
        for shape in remaining_adj_shapes + [parcel_shape]:
            if shape:
                points = shape.split('-')
                for i in range(len(points) - 1):
                    lines_to_keep.add(frozenset([points[i], points[i+1]]))
        log_msg(logFile, f"8. Лінії, що залишаються: {[f'{p1}-{p2}' for p1, p2 in lines_to_keep]}")

        # 9. Фільтруємо множину ліній на видалення
        final_lines_to_delete = lines_candidates_for_deletion - lines_to_keep
        log_msg(logFile, f"9. Лінії, що будуть видалені: {[f'{p1}-{p2}' for p1, p2 in final_lines_to_delete]}")

        # 10. Видаляємо лінії з <Polyline>
        polyline_container = self.root.find('.//Polyline')
        if polyline_container is not None and final_lines_to_delete:
            ulids_to_delete = set()
            for ulid, data in self.polylines.items():
                if frozenset(data['points']) in final_lines_to_delete:
                    ulids_to_delete.add(ulid)
            
            if ulids_to_delete:
                lines_to_remove_elems = [pl['elem'] for ulid, pl in self.polylines.items() if ulid in ulids_to_delete]
                for elem in lines_to_remove_elems:
                    polyline_container.remove(elem)
                log_msg(logFile, f"Видалено {len(lines_to_remove_elems)} ліній з <Polyline>.")

        # 11. Видаляємо точки з <PointInfo>
        point_info_container = self.root.find('.//PointInfo')
        if point_info_container is not None and final_points_to_delete:
            points_to_remove_elems = [pt['elem'] for uidp, pt in self.points.items() if uidp in final_points_to_delete]
            for elem in points_to_remove_elems:
                point_info_container.remove(elem)
            log_msg(logFile, f"Видалено {len(points_to_remove_elems)} точок з <PointInfo>.")

        # 12. Оновлюємо внутрішні кеші процесора
        self.polylines = self._get_all_polylines()
        self.points = self._get_all_points()
        log_msg(logFile, "--- Завершено безпечне очищення геометрії ---")

        # 13. Перенумеровуємо геометрію, щоб усунути прогалини
        self.renumber_geometry()
        log_msg(logFile, "Геометрію (вузли та лінії) було перенумеровано.")

    def renumber_geometry(self):
        """
        Перенумеровує всі вузли (Points) та лінії (Polylines) для усунення прогалин
        та оновлює всі посилання на них у XML-дереві.
        """
        log_msg(logFile, "--- Початок перенумерації геометрії ---")

        # 1. Перенумерація вузлів (Points)
        old_uidp_to_new = {}
        all_points = self.root.findall('.//PointInfo/Point')
        # Сортуємо за старим UIDP, щоб зберегти відносний порядок
        all_points.sort(key=lambda p: int(p.findtext('UIDP', '0')))

        for i, point_elem in enumerate(all_points, 1):
            new_uidp = str(i)
            new_pn = str(i)
            old_uidp = point_elem.findtext('UIDP')

            if old_uidp and old_uidp != new_uidp:
                old_uidp_to_new[old_uidp] = new_uidp

            point_elem.find('UIDP').text = new_uidp
            pn_elem = point_elem.find('PN')
            if pn_elem is not None:
                pn_elem.text = new_pn

        log_msg(logFile, f"Перенумеровано {len(all_points)} вузлів. Створено {len(old_uidp_to_new)} відображень UIDP.")

        # 2. Перенумерація ліній (Polylines)
        old_ulid_to_new = {}
        all_lines = self.root.findall('.//Polyline/PL')
        # Сортуємо за старим ULID
        all_lines.sort(key=lambda pl: int(pl.findtext('ULID', '0')))

        for i, line_elem in enumerate(all_lines, 1):
            new_ulid = str(i)
            old_ulid = line_elem.findtext('ULID')

            if old_ulid and old_ulid != new_ulid:
                old_ulid_to_new[old_ulid] = new_ulid

            line_elem.find('ULID').text = new_ulid

        log_msg(logFile, f"Перенумеровано {len(all_lines)} ліній. Створено {len(old_ulid_to_new)} відображень ULID.")

        # 3. Оновлення посилань на вузли (UIDP) у всіх полілініях
        if old_uidp_to_new:
            updated_p_refs = 0
            for p_ref in self.root.xpath(".//Polyline/PL/Points/P"):
                old_ref = p_ref.text
                if old_ref in old_uidp_to_new:
                    p_ref.text = old_uidp_to_new[old_ref]
                    updated_p_refs += 1
            log_msg(logFile, f"Оновлено {updated_p_refs} посилань на вузли в полілініях.")

        # 4. Оновлення посилань на лінії (ULID) у всіх контурах
        if old_ulid_to_new:
            updated_ulid_refs = 0
            # XPath для пошуку всіх елементів ULID всередині будь-яких контурів
            ulid_refs = self.root.xpath(
                ".//Externals/Boundary/Lines/Line/ULID | "
                ".//Internals/Boundary/Lines/Line/ULID | "
                ".//AdjacentBoundary/Lines/Line/ULID"
            )
            for ulid_ref in ulid_refs:
                old_ref = ulid_ref.text
                if old_ref in old_ulid_to_new:
                    ulid_ref.text = old_ulid_to_new[old_ref]
                    updated_ulid_refs += 1
            log_msg(logFile, f"Оновлено {updated_ulid_refs} посилань на лінії в контурах.")

        # 5. Оновлюємо внутрішні кеші процесора, щоб вони відповідали новому стану
        self.points = self._get_all_points()
        self.polylines = self._get_all_polylines()
        self.max_uidp = self._get_max_id('.//PointInfo/Point', 'UIDP')
        self.max_pn = self._get_max_id('.//PointInfo/Point', 'PN')
        self.max_ulid = self._get_max_id('.//Polyline/PL', 'ULID')

        log_msg(logFile, "--- Завершено перенумерацію геометрії ---")

    def renumber_geometry(self):
        """
        Перенумеровує всі вузли (Points) та лінії (Polylines) для усунення прогалин
        та оновлює всі посилання на них у XML-дереві.
        """
        log_msg(logFile, "--- Початок перенумерації геометрії ---")

        # 1. Перенумерація вузлів (Points)
        old_uidp_to_new = {}
        all_points = self.root.findall('.//PointInfo/Point')
        # Сортуємо за старим UIDP, щоб зберегти відносний порядок
        all_points.sort(key=lambda p: int(p.findtext('UIDP', '0')))

        for i, point_elem in enumerate(all_points, 1):
            new_uidp = str(i)
            new_pn = str(i)
            old_uidp = point_elem.findtext('UIDP')

            if old_uidp and old_uidp != new_uidp:
                old_uidp_to_new[old_uidp] = new_uidp

            point_elem.find('UIDP').text = new_uidp
            pn_elem = point_elem.find('PN')
            if pn_elem is not None:
                pn_elem.text = new_pn

        log_msg(logFile, f"Перенумеровано {len(all_points)} вузлів. Створено {len(old_uidp_to_new)} відображень UIDP.")

        # 2. Перенумерація ліній (Polylines)
        old_ulid_to_new = {}
        all_lines = self.root.findall('.//Polyline/PL')
        # Сортуємо за старим ULID
        all_lines.sort(key=lambda pl: int(pl.findtext('ULID', '0')))

        for i, line_elem in enumerate(all_lines, 1):
            new_ulid = str(i)
            old_ulid = line_elem.findtext('ULID')

            if old_ulid and old_ulid != new_ulid:
                old_ulid_to_new[old_ulid] = new_ulid

            line_elem.find('ULID').text = new_ulid

        log_msg(logFile, f"Перенумеровано {len(all_lines)} ліній. Створено {len(old_ulid_to_new)} відображень ULID.")

        # 3. Оновлення посилань на вузли (UIDP) у всіх полілініях
        if old_uidp_to_new:
            updated_p_refs = 0
            for p_ref in self.root.xpath(".//Polyline/PL/Points/P"):
                old_ref = p_ref.text
                if old_ref in old_uidp_to_new:
                    p_ref.text = old_uidp_to_new[old_ref]
                    updated_p_refs += 1
            log_msg(logFile, f"Оновлено {updated_p_refs} посилань на вузли в полілініях.")

        # 4. Оновлення посилань на лінії (ULID) у всіх контурах
        if old_ulid_to_new:
            updated_ulid_refs = 0
            # XPath для пошуку всіх елементів ULID всередині будь-яких контурів
            ulid_refs = self.root.xpath(
                ".//Externals/Boundary/Lines/Line/ULID | "
                ".//Internals/Boundary/Lines/Line/ULID | "
                ".//AdjacentBoundary/Lines/Line/ULID"
            )
            for ulid_ref in ulid_refs:
                old_ref = ulid_ref.text
                if old_ref in old_ulid_to_new:
                    ulid_ref.text = old_ulid_to_new[old_ref]
                    updated_ulid_refs += 1
            log_msg(logFile, f"Оновлено {updated_ulid_refs} посилань на лінії в контурах.")

        # 5. Оновлюємо внутрішні кеші процесора, щоб вони відповідали новому стану
        self.points = self._get_all_points()
        self.polylines = self._get_all_polylines()
        self.max_uidp = self._get_max_id('.//PointInfo/Point', 'UIDP')
        self.max_pn = self._get_max_id('.//PointInfo/Point', 'PN')
        self.max_ulid = self._get_max_id('.//Polyline/PL', 'ULID')

        log_msg(logFile, "--- Завершено перенумерацію геометрії ---")

    def renumber_geometry(self):
        """
        Перенумеровує всі вузли (Points) та лінії (Polylines) для усунення прогалин
        та оновлює всі посилання на них у XML-дереві.
        """
        log_msg(logFile, "--- Початок перенумерації геометрії ---")

        # 1. Перенумерація вузлів (Points)
        old_uidp_to_new = {}
        all_points = self.root.findall('.//PointInfo/Point')
        # Сортуємо за старим UIDP, щоб зберегти відносний порядок
        all_points.sort(key=lambda p: int(p.findtext('UIDP', '0')))

        for i, point_elem in enumerate(all_points, 1):
            new_uidp = str(i)
            new_pn = str(i)
            old_uidp = point_elem.findtext('UIDP')

            if old_uidp and old_uidp != new_uidp:
                old_uidp_to_new[old_uidp] = new_uidp

            point_elem.find('UIDP').text = new_uidp
            pn_elem = point_elem.find('PN')
            if pn_elem is not None:
                pn_elem.text = new_pn

        log_msg(logFile, f"Перенумеровано {len(all_points)} вузлів. Створено {len(old_uidp_to_new)} відображень UIDP.")

        # 2. Перенумерація ліній (Polylines)
        old_ulid_to_new = {}
        all_lines = self.root.findall('.//Polyline/PL')
        # Сортуємо за старим ULID
        all_lines.sort(key=lambda pl: int(pl.findtext('ULID', '0')))

        for i, line_elem in enumerate(all_lines, 1):
            new_ulid = str(i)
            old_ulid = line_elem.findtext('ULID')

            if old_ulid and old_ulid != new_ulid:
                old_ulid_to_new[old_ulid] = new_ulid

            line_elem.find('ULID').text = new_ulid

        log_msg(logFile, f"Перенумеровано {len(all_lines)} ліній. Створено {len(old_ulid_to_new)} відображень ULID.")

        # 3. Оновлення посилань на вузли (UIDP) у всіх полілініях
        if old_uidp_to_new:
            updated_p_refs = 0
            for p_ref in self.root.xpath(".//Polyline/PL/Points/P"):
                old_ref = p_ref.text
                if old_ref in old_uidp_to_new:
                    p_ref.text = old_uidp_to_new[old_ref]
                    updated_p_refs += 1
            log_msg(logFile, f"Оновлено {updated_p_refs} посилань на вузли в полілініях.")

        # 4. Оновлення посилань на лінії (ULID) у всіх контурах
        if old_ulid_to_new:
            updated_ulid_refs = 0
            # XPath для пошуку всіх елементів ULID всередині будь-яких контурів
            ulid_refs = self.root.xpath(
                ".//Externals/Boundary/Lines/Line/ULID | "
                ".//Internals/Boundary/Lines/Line/ULID | "
                ".//AdjacentBoundary/Lines/Line/ULID"
            )
            for ulid_ref in ulid_refs:
                old_ref = ulid_ref.text
                if old_ref in old_ulid_to_new:
                    ulid_ref.text = old_ulid_to_new[old_ref]
                    updated_ulid_refs += 1
            log_msg(logFile, f"Оновлено {updated_ulid_refs} посилань на лінії в контурах.")

        # 5. Оновлюємо внутрішні кеші процесора, щоб вони відповідали новому стану
        self.points = self._get_all_points()
        self.polylines = self._get_all_polylines()
        self.max_uidp = self._get_max_id('.//PointInfo/Point', 'UIDP')
        self.max_pn = self._get_max_id('.//PointInfo/Point', 'PN')
        self.max_ulid = self._get_max_id('.//Polyline/PL', 'ULID')

        log_msg(logFile, "--- Завершено перенумерацію геометрії ---")

    def process_lease_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію оренди, оновлює PointInfo, Polyline та додає LeaseInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія оренди повинна бути полігоном.")

        # 1. Обробляємо геометрію полігону
        externals_element, _, _, object_shape = self.process_new_geometry(geometry)
        if externals_element is None:
            raise ValueError("Не вдалося обробити геометрію полігону оренди.")

        # 2. Знаходимо або створюємо контейнер <Leases>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        leases_container = parcel_info.find("Leases")
        if leases_container is None:
            log_msg(logFile, "Створення нового розділу <Leases> в XML-дереві.")
            leases_container = etree.Element("Leases")
            insert_element_in_order(parcel_info, leases_container)

        # 3. Створюємо новий <LeaseInfo> з усіма обов'язковими порожніми елементами
        lease_info = etree.SubElement(leases_container, "LeaseInfo")

        # Додаємо порожній LeaseAgreement
        lease_agreement = etree.SubElement(lease_info, "LeaseAgreement")
        
        # Додаємо Leasees -> Leasee
        leasees = etree.SubElement(lease_agreement, "Leasees")
        leasee = etree.SubElement(leasees, "Leasee")
        # За замовчуванням можна додати порожню фіз. особу
        natural_person = etree.SubElement(leasee, "NaturalPerson")
        full_name = etree.SubElement(natural_person, "FullName")
        etree.SubElement(full_name, "LastName").text = " "
        etree.SubElement(full_name, "FirstName").text = " "
        passport = etree.SubElement(natural_person, "Passport")
        etree.SubElement(passport, "DocumentType").text = " "
        etree.SubElement(passport, "PassportNumber").text = " "
        etree.SubElement(passport, "PassportIssuedDate").text = "1900-01-01"
        etree.SubElement(passport, "IssuanceAuthority").text = " "
        etree.SubElement(passport, "PassportSeries").text = " "

        # Додаємо інші обов'язкові елементи
        etree.SubElement(lease_agreement, "Area").text = f"{(geometry.area() / 10000.0):.4f}"
        lease_term = etree.SubElement(lease_agreement, "LeaseTerm")
        etree.SubElement(lease_term, "LeaseDuration").text = " "
        rent = etree.SubElement(lease_agreement, "Rent")
        etree.SubElement(rent, "MoneyRent").text = "0.0"
        etree.SubElement(lease_agreement, "RegistrationNumber").text = " "
        etree.SubElement(lease_agreement, "RegistrationDate").text = "1900-01-01"

        # Додаємо геометрію
        lease_info.append(externals_element)

        log_msg(logFile, f"Додано новий елемент LeaseInfo. object_shape: {object_shape}")

    def process_sublease_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію суборенди, оновлює PointInfo, Polyline та додає SubleaseInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія суборенди повинна бути полігоном.")

        # 1. Обробляємо геометрію полігону
        externals_element, _, _, object_shape = self.process_new_geometry(geometry)
        if externals_element is None:
            raise ValueError("Не вдалося обробити геометрію полігону суборенди.")

        # 2. Знаходимо або створюємо контейнер <Subleases>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        subleases_container = parcel_info.find("Subleases")
        if subleases_container is None:
            log_msg(logFile, "Створення нового розділу <Subleases> в XML-дереві.")
            subleases_container = etree.Element("Subleases")
            insert_element_in_order(parcel_info, subleases_container)

        # 3. Створюємо новий <SubleaseInfo> з усіма обов'язковими порожніми елементами
        sublease_info = etree.SubElement(subleases_container, "SubleaseInfo")

        # Додаємо порожній SubleaseAgreement
        sublease_agreement = etree.SubElement(sublease_info, "SubleaseAgreement")
        
        # Додаємо Subleasees -> Subleasee
        subleasees = etree.SubElement(sublease_agreement, "Subleasees")
        subleasee = etree.SubElement(subleasees, "Subleasee")
        # За замовчуванням можна додати порожню фіз. особу
        natural_person = etree.SubElement(subleasee, "NaturalPerson")
        full_name = etree.SubElement(natural_person, "FullName")
        etree.SubElement(full_name, "LastName").text = " "
        etree.SubElement(full_name, "FirstName").text = " "
        passport = etree.SubElement(natural_person, "Passport")
        etree.SubElement(passport, "DocumentType").text = " "
        etree.SubElement(passport, "PassportNumber").text = " "
        etree.SubElement(passport, "PassportIssuedDate").text = "1900-01-01"
        etree.SubElement(passport, "IssuanceAuthority").text = " "
        etree.SubElement(passport, "PassportSeries").text = " "

        # Додаємо інші обов'язкові елементи
        etree.SubElement(sublease_agreement, "Area").text = f"{(geometry.area() / 10000.0):.4f}"
        sublease_term = etree.SubElement(sublease_agreement, "SubleaseTerm")
        etree.SubElement(sublease_term, "Term").text = " "
        etree.SubElement(sublease_agreement, "RegistrationNumber").text = " "
        etree.SubElement(sublease_agreement, "RegistrationDate").text = "1900-01-01"

        # Додаємо геометрію
        sublease_info.append(externals_element)

        log_msg(logFile, f"Додано новий елемент SubleaseInfo. object_shape: {object_shape}")

    def process_restriction_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію обмеження, оновлює PointInfo, Polyline та додає RestrictionInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія обмеження повинна бути полігоном.")

        # 1. Обробляємо геометрію полігону
        externals_element, _, _, object_shape = self.process_new_geometry(geometry)
        if externals_element is None:
            raise ValueError("Не вдалося обробити геометрію полігону обмеження.")

        # 2. Знаходимо або створюємо контейнер <Restrictions>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        restrictions_container = parcel_info.find("Restrictions")
        if restrictions_container is None:
            log_msg(logFile, "Створення нового розділу <Restrictions> в XML-дереві.")
            restrictions_container = etree.Element("Restrictions")
            insert_element_in_order(parcel_info, restrictions_container)

        # 3. Створюємо новий <RestrictionInfo> з усіма обов'язковими порожніми елементами
        restriction_info = etree.SubElement(restrictions_container, "RestrictionInfo")

        # Додаємо порожні елементи
        etree.SubElement(restriction_info, "RestrictionCode").text = " "
        etree.SubElement(restriction_info, "RestrictionName").text = " "

        # Додаємо порожній RestrictionTerm
        restriction_term = etree.SubElement(restriction_info, "RestrictionTerm")
        time_element = etree.SubElement(restriction_term, "Time")
        etree.SubElement(time_element, "StartDate").text = "1900-01-01"
        etree.SubElement(time_element, "ExpirationDate").text = "1900-01-01"

        # Додаємо геометрію
        restriction_info.append(externals_element)

        log_msg(logFile, f"Додано новий елемент RestrictionInfo. object_shape: {object_shape}")