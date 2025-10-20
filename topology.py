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
        geom_part = qgis_geom.constGet()
        if qgis_geom.isNull() or not isinstance(geom_part, (QgsPolygon, QgsMultiPolygon)):
            return None, None, None

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
                    # --- Кінець виправлення ---

        # Додаємо унікальні нові елементи до головного дерева XML
        point_info_container = self.root.find('.//PointInfo')
        if point_info_container is not None:
            for p_elem in new_points_to_add:
                point_info_container.append(p_elem)

        polyline_container = self.root.find('.//Polyline')
        if polyline_container is not None:
            for pl_elem in new_polylines_to_add:
                polyline_container.append(pl_elem)

        # Додаємо Internals до Externals, щоб повернути єдиний блок
        if internals is not None:
            externals.append(internals)

        return externals, new_points_to_add, new_polylines_to_add

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
        if geometry.wkbType() not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            raise ValueError("Геометрія суміжника повинна бути полілінією.")

        if geometry.type() == QgsWkbTypes.MultiLineString:
            # Беремо першу частину мультилінії
            polyline = geometry.asMultiPolyline()[0]
        else:
            polyline = geometry.asPolyline()

        line_ulids = []
        # 1. Створюємо точки та лінії
        for i in range(len(polyline) - 1):
            p1, p2 = polyline[i], polyline[i+1]
            uidp1 = self._get_or_create_point(p1)
            uidp2 = self._get_or_create_point(p2)
            ulid = self._create_polyline(uidp1, uidp2, p1, p2)
            line_ulids.append(ulid)

        # 2. Знаходимо або створюємо контейнер <AdjacentUnits>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        adjacent_units_container = parcel_info.find("AdjacentUnits")
        if adjacent_units_container is None:
            adjacent_units_container = etree.Element("AdjacentUnits")
            # Вставляємо у правильне місце згідно зі схемою
            insert_element_in_order(parcel_info, adjacent_units_container)

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

        log_msg(logFile, f"Додано нового суміжника з {len(line_ulids)} ліній.")

    def process_lease_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію оренди, оновлює PointInfo, Polyline та додає LeaseInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія оренди повинна бути полігоном.")

        # 1. Обробляємо геометрію полігону
        externals_element, _, _ = self.process_new_geometry(geometry)
        if externals_element is None:
            raise ValueError("Не вдалося обробити геометрію полігону оренди.")

        # 2. Знаходимо або створюємо контейнер <Leases>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        leases_container = parcel_info.find("Leases")
        if leases_container is None:
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

        log_msg(logFile, "Додано новий елемент LeaseInfo з повною структурою.")

    def process_sublease_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію суборенди, оновлює PointInfo, Polyline та додає SubleaseInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія суборенди повинна бути полігоном.")

        # 1. Обробляємо геометрію полігону
        externals_element, _, _ = self.process_new_geometry(geometry)
        if externals_element is None:
            raise ValueError("Не вдалося обробити геометрію полігону суборенди.")

        # 2. Знаходимо або створюємо контейнер <Subleases>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        subleases_container = parcel_info.find("Subleases")
        if subleases_container is None:
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

        log_msg(logFile, "Додано новий елемент SubleaseInfo з повною структурою.")

    def process_restriction_geometry(self, geometry: QgsGeometry):
        """
        Обробляє геометрію обмеження, оновлює PointInfo, Polyline та додає RestrictionInfo
        з усіма обов'язковими порожніми піделементами.
        """
        if geometry.wkbType() not in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
            raise ValueError("Геометрія обмеження повинна бути полігоном.")

        # 1. Обробляємо геометрію полігону
        externals_element, _, _ = self.process_new_geometry(geometry)
        if externals_element is None:
            raise ValueError("Не вдалося обробити геометрію полігону обмеження.")

        # 2. Знаходимо або створюємо контейнер <Restrictions>
        parcel_info = self.root.find(".//ParcelInfo")
        if parcel_info is None:
            raise ValueError("Не знайдено елемент ParcelInfo в XML.")

        restrictions_container = parcel_info.find("Restrictions")
        if restrictions_container is None:
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

        log_msg(logFile, "Додано новий елемент RestrictionInfo з повною структурою.")