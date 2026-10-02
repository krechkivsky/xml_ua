"""Coverage checks for the parcel perimeter and adjacent-unit boundaries."""
from __future__ import annotations

import math


TOLERANCE_M = 0.001


def _uidp(element) -> str | None:
    value = element.findtext("UIDP")
    return str(value).strip() if value and str(value).strip() else None


def _load_geometry(root):
    coords = {}
    for point in root.findall(".//PointInfo/Point"):
        uidp = _uidp(point)
        try:
            # XML stores northing in X and easting in Y; Euclidean length is
            # unchanged by this axis swap.
            coords[uidp] = (float(point.findtext("X")), float(point.findtext("Y")))
        except (TypeError, ValueError):
            continue

    polylines = {}
    for polyline in root.findall(".//Polyline/PL"):
        ulid = polyline.findtext("ULID")
        points = [p.text.strip() for p in polyline.findall("Points/P") if p.text and p.text.strip()]
        if ulid and points:
            polylines[str(ulid).strip()] = points
    return coords, polylines


def _ordered_chain(lines, polylines):
    segments = []
    for line in lines.findall("Line") if lines is not None else ():
        ulid = line.findtext("ULID")
        points = polylines.get(str(ulid).strip()) if ulid else None
        if points and len(points) >= 2:
            segments.append(list(points))
    if not segments:
        return []

    chain = segments.pop(0)
    while segments:
        joined = False
        for i, segment in enumerate(segments):
            if segment[0] == chain[-1]:
                chain.extend(segment[1:])
            elif segment[-1] == chain[-1]:
                chain.extend(reversed(segment[:-1]))
            elif segment[-1] == chain[0]:
                chain = segment[:-1] + chain
            elif segment[0] == chain[0]:
                chain = list(reversed(segment[1:])) + chain
            else:
                continue
            segments.pop(i)
            joined = True
            break
        if not joined:
            # Retain measurable parts of a malformed/disconnected boundary.
            for segment in segments:
                if segment[0] == chain[-1]:
                    chain.extend(segment[1:])
                elif segment[-1] == chain[-1]:
                    chain.extend(reversed(segment[:-1]))
                else:
                    chain.extend(segment)
            break
    return chain


def _chain_length(chain, coords, start=0, end=None):
    if end is None:
        end = len(chain) - 1
    total = 0.0
    for i in range(max(0, start), min(end, len(chain) - 1)):
        a = coords.get(chain[i])
        b = coords.get(chain[i + 1])
        if a is not None and b is not None:
            total += math.hypot(b[0] - a[0], b[1] - a[1])
    return total


def _boundary_limits(chain, closed, parcel_uidps, adjacent_incidence):
    if len(chain) < 2:
        return 0, 0
    if closed or chain[0] == chain[-1]:
        return 0, len(chain) - 1

    shared_indices = [i for i, uidp in enumerate(chain) if uidp in parcel_uidps]
    if len(shared_indices) < 2:
        # Point contacts have no shared boundary segment. Contacts at a node
        # incident to more than three units are explicitly corner adjacencies.
        if shared_indices:
            is_corner = any(
                1 + adjacent_incidence.get(chain[i], 0) > 3
                for i in shared_indices
            )
            if is_corner:
                return 0, 0
        return 0, 0
    return shared_indices[0], shared_indices[-1]


def _geometry_length(points, start, end):
    total = 0.0
    for i in range(max(0, start), min(end, len(points) - 1)):
        total += math.hypot(points[i + 1].x() - points[i].x(), points[i + 1].y() - points[i].y())
    return total


def _shape_key(chain):
    forward = tuple(chain)
    reverse = tuple(reversed(chain))
    return min(forward, reverse) if forward and reverse else forward


def check_adjacent_coverage(xml_tree, adjacent_layer=None, tolerance_m=TOLERANCE_M):
    """Return perimeter, XML/layer coverage totals, and user-readable errors."""
    root = xml_tree.getroot()
    coords, polylines = _load_geometry(root)

    parcel = root.find(".//ParcelInfo/ParcelMetricInfo")
    if parcel is None:
        return {"perimeter": None, "xml_total": None, "layer_total": None, "errors": []}

    parcel_lines = parcel.findall("./Externals/Boundary/Lines")
    parcel_chains = [_ordered_chain(lines, polylines) for lines in parcel_lines]
    parcel_uidps = {uidp for chain in parcel_chains for uidp in chain}
    perimeter = sum(_chain_length(chain, coords) for chain in parcel_chains)
    if not parcel_lines or perimeter <= 0:
        return {"perimeter": None, "xml_total": None, "layer_total": None, "errors": []}

    adjacent_container = root.find(".//ParcelInfo/AdjacentUnits")
    records = []
    for adjacent in adjacent_container.findall("AdjacentUnitInfo") if adjacent_container is not None else ():
        boundaries = []
        for boundary in adjacent.findall("AdjacentBoundary"):
            chain = _ordered_chain(boundary.find("Lines"), polylines)
            closed = (boundary.findtext("Closed") or "").strip().lower() == "true"
            boundaries.append((chain, closed))
        records.append(boundaries)

    # Count the current parcel plus distinct adjacent units incident at each
    # point. A point shared by more than three units is a corner contact.
    adjacent_incidence = {}
    for boundaries in records:
        unit_uidps = {uidp for chain, _closed in boundaries for uidp in chain}
        for uidp in unit_uidps:
            adjacent_incidence[uidp] = adjacent_incidence.get(uidp, 0) + 1

    def boundary_length(chain, closed):
        start, end = _boundary_limits(
            chain, closed, parcel_uidps, adjacent_incidence
        )
        return _chain_length(chain, coords, start, end)

    xml_total = sum(
        boundary_length(chain, closed)
        for boundaries in records
        for chain, closed in boundaries
    )

    layer_total = None
    if adjacent_layer is not None:
        xml_by_shape = {}
        for boundaries in records:
            for chain, closed in boundaries:
                xml_by_shape.setdefault(_shape_key(chain), (chain, closed))
        layer_total = 0.0
        for feature in adjacent_layer.getFeatures():
            shape = str(feature.attribute("object_shape") or "").strip()
            chain = [part for part in shape.split("-") if part]
            if not chain:
                continue
            match = xml_by_shape.get(_shape_key(chain))
            if match:
                source_chain, closed = match
                start, end = _boundary_limits(
                    source_chain, closed, parcel_uidps, adjacent_incidence
                )
                geometry = feature.geometry()
                points = geometry.asPolyline() if not geometry.isNull() else []
                if len(points) == len(source_chain):
                    if chain == list(reversed(source_chain)):
                        points.reverse()
                    layer_total += _geometry_length(points, start, end)
                else:
                    layer_total += _chain_length(source_chain, coords, start, end)
            else:
                closed = len(chain) > 2 and chain[0] == chain[-1]
                start, end = _boundary_limits(
                    chain, closed, parcel_uidps, adjacent_incidence
                )
                geometry = feature.geometry()
                points = geometry.asPolyline() if not geometry.isNull() else []
                layer_total += (
                    _geometry_length(points, start, end)
                    if len(points) == len(chain)
                    else _chain_length(chain, coords, start, end)
                )

    errors = []
    difference = abs(xml_total - perimeter)
    if difference > tolerance_m:
        errors.append(
            f"Блок суміжників: сума довжин {xml_total:.3f} м не дорівнює периметру ділянки {perimeter:.3f} м (різниця {difference:.3f} м)."
        )
    if adjacent_layer is None:
        errors.append("Шар «Суміжники» відсутній, тому його повноту не вдалося перевірити.")
    else:
        difference = abs(layer_total - perimeter)
        if difference > tolerance_m:
            errors.append(
                f"Шар «Суміжники»: сума довжин {layer_total:.3f} м не дорівнює периметру ділянки {perimeter:.3f} м (різниця {difference:.3f} м)."
            )

    return {"perimeter": perimeter, "xml_total": xml_total, "layer_total": layer_total, "errors": errors}
