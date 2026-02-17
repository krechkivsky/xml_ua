

"""
Модуль для обробки та унікалізації геометричних даних в XML.
"""
import math
from lxml import etree as etree
from qgis.core import QgsGeometry, QgsPolygon, QgsMultiPolygon, QgsWkbTypes, QgsPointXY

from .common import log_calls, log_calls, logFile, insert_element_in_order, next_object_id_in_container


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



        self.tolerance = 0.10  # 5 см
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

                polylines_dict[ulid] = {'points': points, 'elem': pl_elem}
        return polylines_dict

    def _get_or_create_point(self, qgs_point):
        """
        Перевіряє, чи існує точка з такими координатами.
        Якщо так, повертає її UIDP. Якщо ні, створює нову точку та повертає її UIDP.
        """

        new_x, new_y = qgs_point.x(), qgs_point.y()

        for uidp, point_data in self.points.items():

            existing_x, existing_y = point_data['x'], point_data['y']
            distance = math.sqrt((new_x - existing_x) **
                                 2 + (new_y - existing_y)**2)

            if distance < self.tolerance:
                log_calls(
                    logFile, f"Знайдено існуючу точку UIDP: {uidp} в межах допуску {self.tolerance}м. Координати ({new_x:.3f}, {new_y:.3f}) замінено на ({existing_x:.3f}, {existing_y:.3f}).")
                return uidp

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

        self.points[str(self.max_uidp)] = {'x': qgs_point.x(
        ), 'y': qgs_point.y(), 'elem': new_point_element}
        log_calls(logFile, f"Створено нову точку з UIDP: {self.max_uidp}")
        return str(self.max_uidp)

    def find_point_uidp(self, qgs_point: QgsPointXY):
        """
        Знаходить UIDP існуючої точки в межах допуску. Не створює нову.
        """
        new_x, new_y = qgs_point.x(), qgs_point.y()

        for uidp, point_data in self.points.items():
            existing_x, existing_y = point_data['x'], point_data['y']
            distance = math.sqrt((new_x - existing_x) **
                                 2 + (new_y - existing_y)**2)

            if distance < self.tolerance:
                return uidp
        return None

    def _create_polyline(self, uidp1, uidp2, p1, p2):
        """Створює новий елемент PL (полілінія) між двома точками."""

        segment_points_set = frozenset([uidp1, uidp2])
        for ulid, polyline_data in self.polylines.items():
            if frozenset(polyline_data['points']) == segment_points_set:
                log_calls(
                    logFile, f"Знайдено існуючу лінію ULID: {ulid}. Використовуємо її.")
                return ulid

        if self.polyline_info is None:
            metric_info = self.root.find(".//MetricInfo")
            self.polyline_info = etree.SubElement(metric_info, "Polyline")

        self.max_ulid += 1
        new_ulid = str(self.max_ulid)
        log_calls(
            logFile, f"Створено нову лінію з ULID: {new_ulid} між точками {uidp1} та {uidp2}.")
        pl_element = etree.Element("PL")
        etree.SubElement(pl_element, "ULID").text = new_ulid
        points_element = etree.SubElement(pl_element, "Points")
        etree.SubElement(points_element, "P").text = uidp1
        etree.SubElement(points_element, "P").text = uidp2


        length = math.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)
        etree.SubElement(pl_element, "Length").text = f"{length:.2f}"

        self.polyline_info.append(pl_element)

        self.polylines[new_ulid] = {
            'points': [uidp1, uidp2], 'elem': pl_element}

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

        polygon = geom_part if isinstance(
            geom_part, QgsPolygon) else geom_part.geometryN(0)

        exterior_ring = polygon.exteriorRing()
        if exterior_ring:
            boundary_ulids, processed_points, processed_polylines = self._process_ring(
                exterior_ring)
            new_points_to_add.extend(processed_points)
            new_polylines_to_add.extend(processed_polylines)

            boundary = etree.SubElement(externals, "Boundary")

            lines = etree.SubElement(boundary, "Lines")
            for ulid in boundary_ulids:
                line_elem = etree.SubElement(lines, "Line")
                etree.SubElement(line_elem, "ULID").text = ulid
            etree.SubElement(boundary, "Closed").text = "true"

            object_shapes.append(self._get_polyline_object_shape(lines))

        internals = None
        if polygon.numInteriorRings() > 0:
            internals = etree.Element("Internals")
            for i in range(polygon.numInteriorRings()):
                interior_ring = polygon.interiorRing(i)
                if interior_ring:
                    boundary_ulids, processed_points, processed_polylines = self._process_ring(
                        interior_ring)
                    new_points_to_add.extend(processed_points)
                    new_polylines_to_add.extend(processed_polylines)

                    boundary = etree.SubElement(internals, "Boundary")

                    lines = etree.SubElement(boundary, "Lines")
                    for ulid in boundary_ulids:
                        line_elem = etree.SubElement(lines, "Line")
                        etree.SubElement(line_elem, "ULID").text = ulid
                    etree.SubElement(boundary, "Closed").text = "true"
                    object_shapes.append(
                        self._get_polyline_object_shape(lines))

        point_info_container = self.root.find('.//PointInfo')
        if point_info_container is not None:

            point_info_container.extend(new_points_to_add)

        polyline_container = self.root.find('.//Polyline')
        if polyline_container is not None:
            polyline_container.extend(new_polylines_to_add)

        if internals is not None:
            externals.append(internals)

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

        ring_uidps = []
        for qgis_point in points_in_ring:
            found_existing = False
            for uidp, data in self.points.items():
                dist = math.sqrt(
                    (qgis_point.x() - data['x'])**2 + (qgis_point.y() - data['y'])**2)
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
                etree.SubElement(
                    p_elem, "X").text = f"{qgis_point.y():.3f}"  # Y -> X
                etree.SubElement(
                    p_elem, "Y").text = f"{qgis_point.x():.3f}"  # X -> Y
                etree.SubElement(p_elem, "H").text = "0.00"
                etree.SubElement(p_elem, "MX").text = "0.05"
                etree.SubElement(p_elem, "MY").text = "0.05"
                etree.SubElement(p_elem, "MH").text = "0.05"
                etree.SubElement(p_elem, "Description").text = ""
                newly_created_points.append(p_elem)
                self.points[new_uidp] = {
                    'x': qgis_point.x(), 'y': qgis_point.y(), 'elem': p_elem}

        final_ring_uidps = []
        if ring_uidps:
            final_ring_uidps.append(ring_uidps[0])
            for i in range(1, len(ring_uidps)):
                if ring_uidps[i] != ring_uidps[i-1]:
                    final_ring_uidps.append(ring_uidps[i])
                else:
                    log_calls(
                        logFile, f"ПОПЕРЕДЖЕННЯ: Видалено помилкове послідовне входження точки UIDP: {ring_uidps[i]} у полігональному об'єкті.")
        ring_uidps = final_ring_uidps

        if len(ring_uidps) > 1 and ring_uidps[0] == ring_uidps[-1]:
            ring_uidps = ring_uidps[:-1]

        if len(ring_uidps) != len(set(ring_uidps)):
            seen = set()
            duplicates = {x for x in ring_uidps if x in seen or seen.add(x)}  # noqa
            object_shape = "-".join(ring_uidps)
            error_msg = f"Критична топологічна помилка: Точка(и) UIDP {list(duplicates)} входять в контур більше одного разу (самоперетин).\n\nObject Shape: {object_shape}\n\nОб'єкт не буде додано."
            log_calls(logFile, error_msg)
            raise ValueError(error_msg)

        for i in range(len(ring_uidps)):
            p1_uidp = ring_uidps[i]
            p2_uidp = ring_uidps[(i + 1) % len(ring_uidps)]
            current_segment_points = {p1_uidp, p2_uidp}

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
                length = math.sqrt(
                    (p2_coords['x'] - p1_coords['x'])**2 + (p2_coords['y'] - p1_coords['y'])**2)
                etree.SubElement(pl_elem, "Length").text = f"{length:.2f}"

                newly_created_polylines.append(pl_elem)
                self.polylines[new_ulid] = {'points': [
                    p1_uidp, p2_uidp], 'elem': pl_elem}

        return boundary_ulids, newly_created_points, newly_created_polylines

    def process_adjacent_unit_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію суміжника, оновлює PointInfo, Polyline та додає AdjacentUnitInfo.
        """

        adj_units_before = self.root.find(".//AdjacentUnits")
        if adj_units_before is None:
            log_calls(logFile, "(початок): Розділ 'AdjacentUnits' ВІДСУТНІЙ.")
        else:
            count = len(adj_units_before.findall("AdjacentUnitInfo"))
            log_calls(
                logFile, f"(початок): Розділ 'AdjacentUnits' ІСНУЄ. Кількість суміжників: {count}.")

        log_calls(logFile)
        if geometry.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            raise ValueError("Геометрія суміжника повинна бути полілінією.")

        if geometry.type() == QgsWkbTypes.MultiLineString:

            polyline = geometry.asMultiPolyline()[0]
        else:
            polyline = geometry.asPolyline()

        line_ulids = []
        point_uidps = []

        for i in range(len(polyline) - 1):
            p1, p2 = polyline[i], polyline[i+1]
            uidp1 = self._get_or_create_point(p1)
            uidp2 = self._get_or_create_point(p2)

            if i == 0:
                point_uidps.append(uidp1)
            point_uidps.append(uidp2)
            ulid = self._create_polyline(uidp1, uidp2, p1, p2)

            if ulid not in line_ulids:
                line_ulids.append(ulid)

        final_point_uidps = [point_uidps[i] for i in range(
            len(point_uidps)) if i == 0 or point_uidps[i] != point_uidps[i-1]]
        if len(final_point_uidps) < len(point_uidps):
            log_calls(
                logFile, "ПОПЕРЕДЖЕННЯ: Видалено помилкові послідовні входження точок у геометрії суміжника.")

        if len(final_point_uidps) != len(set(final_point_uidps)):
            seen = set()
            duplicates = {
                x for x in final_point_uidps if x in seen or seen.add(x)}
            error_msg = f"Критична топологічна помилка: Точка(и) UIDP {list(duplicates)} входять в контур суміжника більше одного разу (самоперетин). Об'єкт не буде додано."
            log_calls(logFile, error_msg)
            raise ValueError(error_msg)

        object_shape = "-".join(point_uidps)

        for adj_unit in self.root.findall(".//AdjacentUnitInfo"):
            existing_ulids = {line.findtext("ULID") for line in adj_unit.findall(
                ".//AdjacentBoundary/Lines/Line")}
            if set(line_ulids) == existing_ulids:

                return  # Виходимо, щоб не створювати дублікат

        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        adjacent_units_container = parcel_info.find("AdjacentUnits")
        if adjacent_units_container is None:
            log_calls(
                logFile, "Розділ 'AdjacentUnits' відсутній. Створюємо новий.")
            adjacent_units_container = etree.Element(
                "AdjacentUnits")  # Створюємо новий елемент

            adj_units_after_creation = self.root.find(".//AdjacentUnits")
            if adj_units_after_creation is None:
                log_calls(
                    logFile, "(після створення контейнера): Розділ 'AdjacentUnits' все ще ВІДСУТНІЙ.")
            else:
                log_calls(
                    logFile, "(після створення контейнера): Розділ 'AdjacentUnits' тепер ІСНУЄ.")
            insert_element_in_order(parcel_info, adjacent_units_container)

        adj_unit_info = etree.SubElement(
            adjacent_units_container, "AdjacentUnitInfo")
        object_id = next_object_id_in_container(adjacent_units_container, "AdjacentUnitInfo")
        adj_unit_info.set("object_id", object_id)

        adj_boundary = etree.SubElement(adj_unit_info, "AdjacentBoundary")
        lines = etree.SubElement(adj_boundary, "Lines")
        for ulid in line_ulids:
            line_el = etree.SubElement(lines, "Line")
            etree.SubElement(line_el, "ULID").text = ulid

        etree.SubElement(adj_boundary, "Closed").text = "false"

        etree.SubElement(adj_unit_info, "Proprietor")

        if adjacent_units_container is not None:
            count = len(adjacent_units_container.findall("AdjacentUnitInfo"))
            log_calls(
                logFile, f"(після додавання елемента): Розділ 'AdjacentUnits' ІСНУЄ. Кількість суміжників: {count}.")
        else:
            log_calls(
                logFile, "(після додавання елемента): Розділ 'AdjacentUnits' несподівано став ВІДСУТНІМ.")

        log_calls(logFile, f"Додано нового суміжника: {object_shape}.")

    def delete_adjacent_by_shape(self, object_shape_to_delete: str):
        """ # noqa
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

            current_shape_points = set()
            for line in boundary_lines:
                ulid = line.findtext("ULID")
                if ulid in self.polylines:
                    current_shape_points.update(self.polylines[ulid]['points'])

            if set(points_to_check) == current_shape_points:
                element_to_delete = adj_unit
                break

        if element_to_delete is not None:
            adjacent_units_container.remove(element_to_delete)
            log_calls(
                logFile, f"Суміжника {object_shape_to_delete} було видалено з XML.")

            if not adjacent_units_container.findall("AdjacentUnitInfo"):
                adjacent_units_container.getparent().remove(adjacent_units_container)
                log_calls(
                    logFile, "Розділ 'AdjacentUnits' став порожнім і був видалений.")

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

            current_shape_points = []

            segments = []
            for line in boundary_lines:
                ulid = line.findtext("ULID")
                if ulid in self.polylines:
                    segments.append(self.polylines[ulid]['points'])

            if segments:  # noqa

                if segments:
                    current_shape_points.extend(segments.pop(0))

                    while segments:
                        last_point = current_shape_points[-1]

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

                            log_calls(
                                logFile, f"ПОПЕРЕДЖЕННЯ: Ланцюжок суміжника розірвано. Залишилось {len(segments)} нез'єднаних сегментів.")
                            break

            current_shape = "-".join(current_shape_points)

            if current_shape not in remaining_shapes:
                elements_to_delete.append(adj_unit)

        for element in elements_to_delete:
            adjacent_units_container.remove(element)

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

        if lines_container is None:

            return ""

        parent_tag = lines_container.getparent(
        ).tag if lines_container.getparent() is not None else "N/A"
        ulids_in_container = [line.findtext('ULID') for line in lines_container.findall(
            'Line') if line.findtext('ULID') is not None]

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

        if segments:

            shape_points.extend(segments.pop(0))

            while segments:
                start_point = shape_points[0]
                end_point = shape_points[-1]
                found_next = False

                for i, seg in enumerate(segments):

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
                    log_calls(
                        logFile, f"ПОПЕРЕДЖЕННЯ: Ланцюжок суміжника розірвано. Залишилось {len(segments)} нез'єднаних сегментів.")
                    break  # Ланцюжок розірвано

        result = "-".join(shape_points)

        return result

    def get_shape_from_qgis_feature(self, feature: 'QgsFeature'):
        """
        Відновлює object_shape для графічного об'єкта QGIS.
        """

        return "-".join(shape_uidps)

    def get_object_shape_from_externals(self, externals_element):
        """
        Відновлює та повертає object_shape для полігонального об'єкта
        (ділянка, угіддя, оренда тощо) з його елемента <Externals>.
        """
        if externals_element is None:
            return ""

        exterior_shape = self._get_polyline_object_shape(
            externals_element.find("Boundary/Lines"))
        interior_shapes = []
        internals_container = externals_element.find("Internals")
        if internals_container is not None:
            interior_shapes = [self._get_polyline_object_shape(internal.find(
                "Boundary/Lines")) for internal in internals_container.findall("Boundary")]

        all_rings = [exterior_shape] + interior_shapes
        return "|".join(filter(None, all_rings))

    def cleanup_and_renumber_geometry(self):
        """
        Виконує повне очищення та перенумерацію геометрії згідно з алгоритмом.
        Повертає True, якщо були внесені зміни (видалення або перенумерація), інакше False.
        """

        initial_state = etree.tostring(self.root)

        used_ulids = set()

        xpath_for_ulids = ".//Externals/Boundary/Lines/Line/ULID | .//Internals/Boundary/Lines/Line/ULID | .//AdjacentBoundary/Lines/Line/ULID"
        for line_ref in self.root.xpath(xpath_for_ulids):
            if line_ref.text:
                used_ulids.add(line_ref.text)

        polyline_container = self.root.find(
            './/Polyline')  # Блок опису поліліній
        lines_removed_count = 0
        lines_removed_str = ""
        if polyline_container is not None:
            for pl in list(polyline_container):
                ulid = pl.findtext('ULID')
                if ulid not in used_ulids:
                    polyline_container.remove(pl)
                    lines_removed_count += 1
                    lines_removed_str += ulid + ','
        if lines_removed_count > 0:
            log_calls(
                logFile, f"2. Видалено {lines_removed_count} поліліній: {lines_removed_str}")

        used_uidps = set()
        if polyline_container is not None:
            for p_ref in polyline_container.xpath('.//PL/Points/P'):
                if p_ref.text:
                    used_uidps.add(p_ref.text)

        point_info_container = self.root.find('.//PointInfo')
        points_removed_count = 0
        if point_info_container is not None:
            for point in list(point_info_container):
                uidp = point.findtext('UIDP')
                if uidp not in used_uidps:
                    point_info_container.remove(point)
                    points_removed_count += 1
        if points_removed_count > 0:
            log_calls(
                logFile, f"4. Видалено {points_removed_count} невикористовуваних точок (<Point>).")

        self.renumber_geometry()

        final_state = etree.tostring(self.root)
        if initial_state != final_state:
            log_calls(
                logFile, "--- Завершено очищення та перенумерацію. Зміни внесено. ---")
            return True
        else:

            return False

    def renumber_geometry(self):
        """
        Перенумеровує всі вузли (Points) та лінії (Polylines) для усунення прогалин
        та оновлює всі посилання на них у XML-дереві.
        """

        old_uidp_to_new = {}
        all_points = self.root.findall('.//PointInfo/Point')

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

        old_ulid_to_new = {}
        all_lines = self.root.findall('.//Polyline/PL')

        all_lines.sort(key=lambda pl: int(pl.findtext('ULID', '0')))

        for i, line_elem in enumerate(all_lines, 1):
            new_ulid = str(i)
            old_ulid = line_elem.findtext('ULID')

            if old_ulid and old_ulid != new_ulid:
                old_ulid_to_new[old_ulid] = new_ulid

            line_elem.find('ULID').text = new_ulid

        if old_uidp_to_new:
            updated_p_refs = 0
            for p_ref in self.root.xpath(".//Polyline/PL/Points/P"):
                old_ref = p_ref.text
                if old_ref in old_uidp_to_new:
                    p_ref.text = old_uidp_to_new[old_ref]
                    updated_p_refs += 1
            log_calls(
                logFile, f"Оновлено {updated_p_refs} посилань на вузли в полілініях.")

        if old_ulid_to_new:
            updated_ulid_refs = 0

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
            log_calls(
                logFile, f"Оновлено {updated_ulid_refs} посилань на лінії в контурах.")

        self.points = self._get_all_points()
        self.polylines = self._get_all_polylines()
        self.max_uidp = self._get_max_id('.//PointInfo/Point', 'UIDP')
        self.max_pn = self._get_max_id('.//PointInfo/Point', 'PN')
        self.max_ulid = self._get_max_id('.//Polyline/PL', 'ULID')

    def process_lease_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію оренди, оновлює PointInfo, Polyline та додає LeaseInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія оренди повинна бути полігоном.")

        externals_element, _, _, object_shape = self.process_new_geometry(
            geometry)
        if externals_element is None:
            raise ValueError("Не вдалося обробити геометрію полігону оренди.")

        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        leases_container = parcel_info.find("Leases")
        if leases_container is None:
            log_calls(logFile, "Створення нового розділу <Leases> в XML-дереві.")
            leases_container = etree.Element("Leases")
            insert_element_in_order(parcel_info, leases_container)

        lease_info = etree.SubElement(leases_container, "LeaseInfo")
        object_id = next_object_id_in_container(leases_container, "LeaseInfo")
        lease_info.set("object_id", object_id)

        lease_agreement = etree.SubElement(lease_info, "LeaseAgreement")

        leasees = etree.SubElement(lease_agreement, "Leasees")
        leasee = etree.SubElement(leasees, "Leasee")

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

        etree.SubElement(
            lease_agreement, "Area").text = f"{(geometry.area() / 10000.0):.4f}"
        lease_term = etree.SubElement(lease_agreement, "LeaseTerm")
        etree.SubElement(lease_term, "LeaseDuration").text = " "
        rent = etree.SubElement(lease_agreement, "Rent")
        etree.SubElement(rent, "MoneyRent").text = "0.0"
        etree.SubElement(lease_agreement, "RegistrationNumber").text = " "
        etree.SubElement(
            lease_agreement, "RegistrationDate").text = "1900-01-01"

        lease_info.append(externals_element)

        log_calls(
            logFile, f"Додано новий елемент LeaseInfo. object_shape: {object_shape}")

        return object_id, object_shape

    def process_sublease_geometry(self, geometry: QgsGeometry):  # noqa
        """
        Обробляє геометрію суборенди, оновлює PointInfo, Polyline та додає SubleaseInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія суборенди повинна бути полігоном.")

        externals_element, _, _, object_shape = self.process_new_geometry(
            geometry)
        if externals_element is None:
            raise ValueError(
                "Не вдалося обробити геометрію полігону суборенди.")

        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        subleases_container = parcel_info.find("Subleases")
        if subleases_container is None:
            log_calls(
                logFile, "Створення нового розділу <Subleases> в XML-дереві.")
            subleases_container = etree.Element("Subleases")
            insert_element_in_order(parcel_info, subleases_container)

        sublease_info = etree.SubElement(subleases_container, "SubleaseInfo")
        object_id = next_object_id_in_container(subleases_container, "SubleaseInfo")
        sublease_info.set("object_id", object_id)

        subleasees = etree.SubElement(sublease_info, "Subleasees")
        subleasee = etree.SubElement(subleasees, "Subleasee")

        natural_person = etree.SubElement(subleasee, "NaturalPerson")
        full_name = etree.SubElement(natural_person, "FullName")
        etree.SubElement(full_name, "LastName").text = " "
        etree.SubElement(full_name, "FirstName").text = " "
        etree.SubElement(full_name, "MiddleName").text = " "
        passport = etree.SubElement(natural_person, "Passport")
        etree.SubElement(passport, "DocumentType").text = " "
        etree.SubElement(passport, "PassportNumber").text = " "
        etree.SubElement(passport, "PassportIssuedDate").text = "1900-01-01"
        etree.SubElement(passport, "IssuanceAuthority").text = " "
        etree.SubElement(passport, "PassportSeries").text = " "
        address = etree.SubElement(natural_person, "Address")
        etree.SubElement(address, "Region").text = " "
        etree.SubElement(address, "District").text = " "
        etree.SubElement(address, "Settlement").text = " "
        etree.SubElement(address, "Street").text = " "
        etree.SubElement(address, "Building").text = " "

        etree.SubElement(
            sublease_info, "Area").text = f"{(geometry.area() / 10000.0):.4f}"
        etree.SubElement(sublease_info, "RegistrationDate").text = "1900-01-01"
        etree.SubElement(sublease_info, "RegistrationNumber").text = " "
        subrent = etree.SubElement(sublease_info, "Subrent")
        etree.SubElement(subrent, "MoneySubrent").text = "0.0"
        etree.SubElement(sublease_info, "SubleaseTerm")

        sublease_info.append(externals_element)

        log_calls(
            logFile, f"Додано новий елемент SubleaseInfo. object_shape: {object_shape}")

        return object_id, object_shape

    def process_restriction_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію обмеження, оновлює PointInfo, Polyline та додає RestrictionInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія обмеження повинна бути полігоном.")

        externals_element, _, _, object_shape = self.process_new_geometry(
            geometry)
        if externals_element is None:
            raise ValueError(
                "Не вдалося обробити геометрію полігону обмеження.")

        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        restrictions_container = parcel_info.find("Restrictions")
        if restrictions_container is None:
            log_calls(
                logFile, "Створення нового розділу <Restrictions> в XML-дереві.")
            restrictions_container = etree.Element("Restrictions")
            insert_element_in_order(parcel_info, restrictions_container)

        restriction_info = etree.SubElement(
            restrictions_container, "RestrictionInfo")
        object_id = next_object_id_in_container(restrictions_container, "RestrictionInfo")
        restriction_info.set("object_id", object_id)

        etree.SubElement(restriction_info, "RestrictionCode").text = " "
        etree.SubElement(restriction_info, "RestrictionName").text = " "

        restriction_term = etree.SubElement(
            restriction_info, "RestrictionTerm")
        time_element = etree.SubElement(restriction_term, "Time")
        etree.SubElement(time_element, "StartDate").text = "1900-01-01"
        etree.SubElement(time_element, "ExpirationDate").text = "1900-01-01"

        restriction_info.append(externals_element)

        log_calls(
            logFile, f"Додано новий елемент RestrictionInfo. object_shape: {object_shape}")

        return object_id, object_shape

    def add_land_parcel_info(self, externals_element, land_code, size_ha, object_shape):
        """
        Додає новий елемент LandParcelInfo до XML-дерева.
        """
        parcel_info_element = self.root.find(".//ParcelInfo")
        if parcel_info_element is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        lands_parcel_element = parcel_info_element.find("LandsParcel")
        if lands_parcel_element is None:
            log_calls(logFile, "Розділ 'LandsParcel' відсутній. Створюємо новий.")
            lands_parcel_element = etree.Element("LandsParcel")
            insert_element_in_order(parcel_info_element, lands_parcel_element)

        land_parcel_info = etree.SubElement(
            lands_parcel_element, "LandParcelInfo")
        object_id = next_object_id_in_container(lands_parcel_element, "LandParcelInfo")
        land_parcel_info.set("object_id", object_id)

        etree.SubElement(land_parcel_info, "LandCode").text = land_code
        metric_info = etree.SubElement(land_parcel_info, "MetricInfo")
        area = etree.SubElement(metric_info, "Area")
        etree.SubElement(area, "Size").text = f"{size_ha:.4f}"
        etree.SubElement(area, "MeasurementUnit").text = "га"
        if externals_element is not None:
            metric_info.append(externals_element)
        log_calls(
            logFile, f"Додано новий елемент LandParcelInfo. object_id: {object_id}, object_shape: {object_shape}")
        return object_id
