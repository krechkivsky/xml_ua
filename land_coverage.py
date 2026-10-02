"""Geometry and completeness checks for land parcels."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from itertools import combinations

from qgis.core import QgsGeometry, QgsPointXY

from .topology import GeometryProcessor


AREA_TOLERANCE_M2 = 0.1 
GEOMETRY_EPSILON_M2 = 1e-9


def _ring(lines, processor):
    if lines is None:
        return []
    shape = processor._get_polyline_object_shape(lines)
    points = []
    for uidp in (part.strip() for part in shape.split("-")):
        if not uidp:
            continue
        point = processor.points.get(uidp)
        if point is None:
            return []
        points.append(QgsPointXY(point["x"], point["y"]))
    if len(points) >= 3 and points[0] != points[-1]:
        points.append(points[0])
    return points if len(points) >= 4 else []


def _geometry_from_externals(externals, processor):
    if externals is None:
        return QgsGeometry(), ""
    shells = [
        ring for boundary in externals.findall("Boundary")
        if (ring := _ring(boundary.find("Lines"), processor))
    ]
    if not shells:
        return QgsGeometry(), processor.get_object_shape_from_externals(externals)

    shell_geometries = [QgsGeometry.fromPolygonXY([shell]) for shell in shells]
    polygons = [[shell] for shell in shells]
    internals = externals.find("Internals")
    if internals is not None:
        for boundary in internals.findall("Boundary"):
            hole = _ring(boundary.find("Lines"), processor)
            if not hole:
                continue
            # A vertex is more reliable than the centroid for concave holes.
            point = QgsGeometry.fromPointXY(hole[0])
            owner = next(
                (i for i, shell_geometry in enumerate(shell_geometries)
                 if shell_geometry.contains(point)),
                None,
            )
            if owner is not None:
                polygons[owner].append(hole)

    geometry = QgsGeometry.fromMultiPolygonXY(polygons)
    if not geometry.isGeosValid():
        geometry = geometry.makeValid()
    return geometry, processor.get_object_shape_from_externals(externals)


def _shape_key(shape):
    rings = []
    for ring in str(shape or "").split("|"):
        uidps = tuple(part.strip() for part in ring.split("-") if part.strip())
        if uidps:
            rings.append(min(uidps, tuple(reversed(uidps))))
    return tuple(sorted(rings))


def _geometry_problems(records, parcel_geometry, source):
    errors_by_index = {}
    errors = []

    def add(index, message):
        if index is not None:
            errors_by_index.setdefault(index, []).append(message)
        errors.append(message)

    for (index_a, geometry_a, _), (index_b, geometry_b, _) in combinations(records, 2):
        try:
            overlap_area = geometry_a.intersection(geometry_b).area()
        except Exception:
            add(index_a, f"{source}: не вдалося перевірити перетин геометрій.")
            add(index_b, f"{source}: не вдалося перевірити перетин геометрій.")
            continue
        if overlap_area > GEOMETRY_EPSILON_M2:
            label_a = f"Угіддя {index_a}" if index_a is not None else "об'єкт шару"
            label_b = f"Угіддя {index_b}" if index_b is not None else "об'єкт шару"
            add(index_a, f"{source}: {label_a} перекривається з {label_b} на {overlap_area:.6f} м².")
            add(index_b, f"{source}: {label_b} перекривається з {label_a} на {overlap_area:.6f} м².")

    for index, geometry, _ in records:
        try:
            outside_area = geometry.difference(parcel_geometry).area()
        except Exception:
            add(index, f"{source}: не вдалося перевірити вихід за межі ділянки.")
            continue
        if outside_area > GEOMETRY_EPSILON_M2:
            label = f"Угіддя {index}" if index is not None else "об'єкт шару"
            add(index, f"{source}: {label} виходить за межі ділянки на {outside_area:.6f} м².")
    return errors_by_index, errors


def check_land_coverage(xml_tree, lands_layer=None, area_tolerance_m2=AREA_TOLERANCE_M2):
    """Check XML and layer land polygons against the parcel geometry."""
    root = xml_tree.getroot()
    processor = GeometryProcessor(xml_tree)
    parcel_metric = root.find(".//ParcelInfo/ParcelMetricInfo")
    parcel_externals = parcel_metric.find("Externals") if parcel_metric is not None else None
    parcel_geometry, _ = _geometry_from_externals(parcel_externals, processor)
    if parcel_geometry.isEmpty():
        message = "Не вдалося визначити геометрію ділянки для перевірки угідь."
        return {"errors": [message], "block_errors": [message], "land_errors": {}, "parcel_area": None}

    parcel_area = parcel_geometry.area()
    parcel_info = parcel_metric.getparent()
    lands_container = parcel_info.find("LandsParcel") if parcel_info is not None else None
    land_infos = lands_container.findall("LandParcelInfo") if lands_container is not None else []
    land_errors = {}
    block_errors = []
    xml_records = []
    for index, land_info in enumerate(land_infos, 1):
        metric = land_info.find("MetricInfo")
        externals = metric.find("Externals") if metric is not None else None
        geometry, shape = _geometry_from_externals(externals, processor)
        if geometry.isEmpty():
            land_errors.setdefault(index, []).append(f"Угіддя {index}: відсутня або некоректна геометрія.")
        else:
            xml_records.append((index, geometry, _shape_key(shape)))

    xml_issues, xml_messages = _geometry_problems(xml_records, parcel_geometry, "Блок угідь")
    for index, messages in xml_issues.items():
        land_errors.setdefault(index, []).extend(messages)
    xml_area = sum(geometry.area() for _, geometry, _ in xml_records)
    difference = abs(xml_area - parcel_area)
    if difference > area_tolerance_m2:
        block_errors.append(
            f"Блок угідь (XML): сума площ {xml_area:.9f} м² не дорівнює площі ділянки "
            f"{parcel_area:.9f} м² (різниця {difference:.9f} м²)."
        )

    errors = list(xml_messages) + list(block_errors)
    if lands_layer is None:
        block_errors.append("Шар «Угіддя» відсутній, тому його повноту не вдалося перевірити.")
        errors.append(block_errors[-1])
    else:
        xml_by_shape = defaultdict(deque)
        for index, _, key in xml_records:
            if key:
                xml_by_shape[key].append(index)
        layer_records = []
        for feature_index, feature in enumerate(lands_layer.getFeatures(), 1):
            geometry = feature.geometry()
            if geometry is None or geometry.isNull() or geometry.isEmpty():
                message = f"Шар «Угіддя»: об'єкт {feature_index} не має геометрії."
                block_errors.append(message)
                errors.append(message)
                continue
            shape_key = _shape_key(feature.attribute("object_shape"))
            land_index = xml_by_shape[shape_key].popleft() if xml_by_shape[shape_key] else None
            layer_records.append((land_index, geometry, shape_key))

        xml_shape_counts = Counter(key for _, _, key in xml_records if key)
        layer_shape_counts = Counter(key for _, _, key in layer_records if key)
        if xml_shape_counts != layer_shape_counts:
            missing_count = sum((xml_shape_counts - layer_shape_counts).values())
            extra_count = sum((layer_shape_counts - xml_shape_counts).values())
            message = (
                f"Шар «Угіддя» не відповідає блоку XML: відсутніх об'єктів {missing_count}, "
                f"зайвих або змінених {extra_count}."
            )
            block_errors.append(message)
            errors.append(message)

        layer_issues, layer_messages = _geometry_problems(layer_records, parcel_geometry, "Шар «Угіддя»")
        for index, messages in layer_issues.items():
            land_errors.setdefault(index, []).extend(messages)
        errors.extend(layer_messages)
        layer_area = sum(geometry.area() for _, geometry, _ in layer_records)
        difference = abs(layer_area - parcel_area)
        if difference > area_tolerance_m2:
            message = (
                f"Блок угідь (шар): сума площ {layer_area:.9f} м² не дорівнює площі ділянки "
                f"{parcel_area:.9f} м² (різниця {difference:.9f} м²)."
            )
            block_errors.append(message)
            errors.append(message)

    return {"errors": errors, "block_errors": block_errors, "land_errors": land_errors, "parcel_area": parcel_area}
