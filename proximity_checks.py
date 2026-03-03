from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable


ProgressCb = Callable[[int], None]


@dataclass(frozen=True)
class ClosePointHit:
    uidp: str
    other_uidp: str
    distance_m: float


@dataclass(frozen=True)
class NearLineHit:
    uidp: str
    ulid: str
    distance_m: float


@dataclass(frozen=True)
class ProximityCheckResult:
    threshold_m: float
    points_total: int
    points_parsed: int
    polylines_total: int
    segments_total: int
    close_hits: tuple[ClosePointHit, ...]
    near_line_hits: tuple[NearLineHit, ...]
    elapsed_sec: float


def _parse_point_xy(point_elem) -> tuple[float, float] | None:
    """
    Повертає (x, y) в метрах.
    У цьому проєкті X/Y в XML читаються як: y <- X, x <- Y.
    """
    try:
        y = float(point_elem.findtext("X"))
        x = float(point_elem.findtext("Y"))
        return x, y
    except (TypeError, ValueError):
        return None


def _cell_key(x: float, y: float, cell: float) -> tuple[int, int]:
    return (int(math.floor(x / cell)), int(math.floor(y / cell)))


def _dist2(ax: float, ay: float, bx: float, by: float) -> float:
    dx = ax - bx
    dy = ay - by
    return dx * dx + dy * dy


def _point_segment_dist2(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    denom = abx * abx + aby * aby
    if denom <= 0.0:
        return _dist2(px, py, ax, ay)
    t = (apx * abx + apy * aby) / denom
    if t <= 0.0:
        return _dist2(px, py, ax, ay)
    if t >= 1.0:
        return _dist2(px, py, bx, by)
    cx = ax + t * abx
    cy = ay + t * aby
    return _dist2(px, py, cx, cy)


def _sort_uidp(uidp: str):
    s = str(uidp)
    return int(s) if s.isdigit() else 10**18


def find_close_points(*, xml_tree, threshold_m: float, progress: ProgressCb | None = None) -> tuple[ClosePointHit, ...]:
    """
    Близькі точки: для кожного UIDP повертає найближчу іншу точку (UIDP) з відстанню < threshold_m.
    """
    root = xml_tree.getroot()
    point_elems = root.findall(".//PointInfo/Point")

    cell = max(0.01, float(threshold_m))
    thr2 = threshold_m * threshold_m

    grid: dict[tuple[int, int], list[tuple[str, float, float]]] = {}
    best: dict[str, tuple[str, float]] = {}  # uidp -> (other_uidp, best_d2)

    total = len(point_elems)
    for idx, p in enumerate(point_elems, 1):
        uidp = p.findtext("UIDP")
        if not uidp or not str(uidp).strip():
            continue
        xy = _parse_point_xy(p)
        if xy is None:
            continue
        x, y = xy

        ck = _cell_key(x, y, cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                bucket = grid.get((ck[0] + dx, ck[1] + dy))
                if not bucket:
                    continue
                for other_uidp, ox, oy in bucket:
                    d2 = _dist2(x, y, ox, oy)
                    if d2 < thr2:
                        uidp_s = str(uidp).strip()
                        other_s = str(other_uidp).strip()
                        prev = best.get(uidp_s)
                        if prev is None or d2 < prev[1]:
                            best[uidp_s] = (other_s, d2)
                        prev_other = best.get(other_s)
                        if prev_other is None or d2 < prev_other[1]:
                            best[other_s] = (uidp_s, d2)

        grid.setdefault(ck, []).append((str(uidp).strip(), x, y))

        if progress and (idx % 500 == 0 or idx == total):
            # 0..50
            progress(int(50 * idx / max(1, total)))

    hits: list[ClosePointHit] = []
    for uidp_s, (other_s, d2) in best.items():
        hits.append(ClosePointHit(uidp=uidp_s, other_uidp=other_s, distance_m=math.sqrt(d2)))
    hits.sort(key=lambda h: _sort_uidp(h.uidp))
    return tuple(hits)


@dataclass(frozen=True)
class _Segment:
    ax: float
    ay: float
    bx: float
    by: float
    poly_idx: int
    ulid: str


def _iter_polylines(xml_tree) -> Iterable[tuple[list[str], object]]:
    root = xml_tree.getroot()
    for pl in root.findall(".//Polyline/PL"):
        ulid = pl.findtext("ULID")
        uidps = []
        for p in pl.findall("Points/P"):
            if p.text and str(p.text).strip():
                uidps.append(str(p.text).strip())
        yield uidps, ulid, pl


def find_points_near_lines(
    *,
    xml_tree,
    threshold_m: float,
    progress: ProgressCb | None = None,
) -> tuple[tuple[NearLineHit, ...], int, int]:
    """
    Створні точки: UIDP таких точок, що відстань до будь-якого сегмента будь-якої лінії < threshold_m.

    Важливо: щоб не позначати всі вузли як "створні" (бо вони лежать на своїх лініях),
    точки НЕ перевіряються відносно лінії, в якій вони використані (Polyline/PL/Points/P).
    """
    root = xml_tree.getroot()

    point_elems = root.findall(".//PointInfo/Point")
    points: list[tuple[str, float, float]] = []
    uidp_to_xy: dict[str, tuple[float, float]] = {}
    for p in point_elems:
        uidp = p.findtext("UIDP")
        if not uidp or not str(uidp).strip():
            continue
        xy = _parse_point_xy(p)
        if xy is None:
            continue
        uidp = str(uidp).strip()
        x, y = xy
        points.append((uidp, x, y))
        uidp_to_xy[uidp] = (x, y)

    polylines = list(_iter_polylines(xml_tree))
    poly_uidps: list[set[str]] = [set(uidps) for uidps, _, _ in polylines]

    segments: list[_Segment] = []
    for poly_idx, (uidps, ulid, _) in enumerate(polylines):
        if len(uidps) < 2:
            continue
        for i in range(len(uidps) - 1):
            a = uidps[i]
            b = uidps[i + 1]
            axy = uidp_to_xy.get(a)
            bxy = uidp_to_xy.get(b)
            if axy is None or bxy is None:
                continue
            ax, ay = axy
            bx, by = bxy
            segments.append(_Segment(ax=ax, ay=ay, bx=bx, by=by, poly_idx=poly_idx, ulid=str(ulid or "").strip()))

    # Індекс сегментів по сітці
    cell = 1.0
    thr = float(threshold_m)
    seg_grid: dict[tuple[int, int], list[int]] = {}
    for si, s in enumerate(segments):
        min_x = min(s.ax, s.bx) - thr
        max_x = max(s.ax, s.bx) + thr
        min_y = min(s.ay, s.by) - thr
        max_y = max(s.ay, s.by) + thr
        cx0, cy0 = _cell_key(min_x, min_y, cell)
        cx1, cy1 = _cell_key(max_x, max_y, cell)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                seg_grid.setdefault((cx, cy), []).append(si)

    thr2 = thr * thr
    best: dict[str, tuple[str, float]] = {}  # uidp -> (ulid, best_d2)

    total = len(points)
    for idx, (uidp, x, y) in enumerate(points, 1):
        ck = _cell_key(x, y, cell)
        candidate_seg_ids: set[int] = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                ids = seg_grid.get((ck[0] + dx, ck[1] + dy))
                if ids:
                    candidate_seg_ids.update(ids)

        for si in candidate_seg_ids:
            s = segments[si]
            if uidp in poly_uidps[s.poly_idx]:
                continue
            d2 = _point_segment_dist2(x, y, s.ax, s.ay, s.bx, s.by)
            if d2 < thr2:
                ulid = s.ulid or "?"
                prev = best.get(uidp)
                if prev is None or d2 < prev[1]:
                    best[uidp] = (ulid, d2)

        if progress and (idx % 300 == 0 or idx == total):
            # 50..100
            progress(50 + int(50 * idx / max(1, total)))

    hits: list[NearLineHit] = []
    for uidp_s, (ulid, d2) in best.items():
        hits.append(NearLineHit(uidp=uidp_s, ulid=ulid, distance_m=math.sqrt(d2)))
    hits.sort(key=lambda h: _sort_uidp(h.uidp))
    return tuple(hits), len(polylines), len(segments)


def run_proximity_checks(
    *,
    xml_tree,
    threshold_m: float = 0.3,
    progress: ProgressCb | None = None,
) -> ProximityCheckResult:
    started = time.time()

    root = xml_tree.getroot()
    points_total = len(root.findall(".//PointInfo/Point"))

    close_hits = find_close_points(xml_tree=xml_tree, threshold_m=threshold_m, progress=progress)
    near_line_hits, polylines_total, segments_total = find_points_near_lines(
        xml_tree=xml_tree, threshold_m=threshold_m, progress=progress
    )

    elapsed = time.time() - started

    # Parsed points = those with UIDP + valid coords
    parsed = 0
    for p in root.findall(".//PointInfo/Point"):
        uidp = p.findtext("UIDP")
        if not uidp or not str(uidp).strip():
            continue
        if _parse_point_xy(p) is None:
            continue
        parsed += 1

    return ProximityCheckResult(
        threshold_m=float(threshold_m),
        points_total=points_total,
        points_parsed=parsed,
        polylines_total=polylines_total,
        segments_total=segments_total,
        close_hits=close_hits,
        near_line_hits=near_line_hits,
        elapsed_sec=float(elapsed),
    )


def proximity_report_path(xml_path: str) -> str:
    p = Path(xml_path)
    return str(p.with_name(f"{p.stem}_proximity.txt"))


def build_proximity_report(*, xml_path: str, result: ProximityCheckResult) -> str:
    out: list[str] = []
    out.append(f"Файл: {xml_path}")
    out.append(f"Дата/час: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    out.append(f"Поріг: {result.threshold_m} м")
    out.append(f"Точок: {result.points_parsed}/{result.points_total}, Ліній: {result.polylines_total}, Сегментів: {result.segments_total}")
    out.append(f"Час: {result.elapsed_sec:.2f} сек")
    out.append("")

    out.append("1. Близькі Вузли:")
    if not result.close_hits:
        out.append("  немає")
    else:
        for i, hit in enumerate(result.close_hits, 1):
            out.append(
                f"  {i}. Точка {hit.uidp} близька до точки {hit.other_uidp}  {hit.distance_m:.3f}"
            )
    out.append("")

    out.append("2. Створні точки:")
    if not result.near_line_hits:
        out.append("  немає")
    else:
        for i, hit in enumerate(result.near_line_hits, 1):
            out.append(
                f"  {i}. Точка {hit.uidp} близька до лінії {hit.ulid}  {hit.distance_m:.3f}"
            )

    return "\n".join(out) + "\n"


def write_proximity_report(*, xml_path: str, report_text: str) -> str:
    report_path = proximity_report_path(xml_path)
    Path(report_path).write_text(report_text, encoding="utf-8")
    return report_path
