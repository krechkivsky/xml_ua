from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ULID_REF_XPATH = (
    ".//Externals/Boundary/Lines/Line/ULID | "
    ".//Internals/Boundary/Lines/Line/ULID | "
    ".//AdjacentBoundary/Lines/Line/ULID"
)

P_REF_XPATH = ".//Polyline/PL/Points/P"


@dataclass(frozen=True)
class PointState:
    elem: object
    uidp: str
    pn: str
    x: str
    y: str


@dataclass(frozen=True)
class LineState:
    elem: object
    ulid: str
    point_refs: tuple[str, ...]


@dataclass(frozen=True)
class RefState:
    elem: object
    value: str


@dataclass(frozen=True)
class GeometryNumberingSnapshot:
    points: tuple[PointState, ...]
    lines: tuple[LineState, ...]
    polyline_point_refs: tuple[RefState, ...]
    boundary_ulid_refs: tuple[RefState, ...]


def _safe_text(value: object) -> str:
    return "" if value is None else str(value)


def snapshot_geometry_numbering(xml_tree) -> GeometryNumberingSnapshot:
    """
    Знімає "зріз" нумерації вузлів (PointInfo/Point) та ліній (Polyline/PL),
    а також усіх посилань на них.

    Важливо: snapshot зберігає посилання на lxml-елементи (elem). Це дозволяє
    після зміни дерева порівняти "до/після" для того ж самого елемента.
    """
    root = xml_tree.getroot()

    points: list[PointState] = []
    for point in root.findall(".//PointInfo/Point"):
        points.append(
            PointState(
                elem=point,
                uidp=_safe_text(point.findtext("UIDP")),
                pn=_safe_text(point.findtext("PN")),
                x=_safe_text(point.findtext("X")),
                y=_safe_text(point.findtext("Y")),
            )
        )

    lines: list[LineState] = []
    for pl in root.findall(".//Polyline/PL"):
        lines.append(
            LineState(
                elem=pl,
                ulid=_safe_text(pl.findtext("ULID")),
                point_refs=tuple(_safe_text(p.text) for p in pl.findall("Points/P")),
            )
        )

    polyline_point_refs = tuple(
        RefState(elem=el, value=_safe_text(el.text)) for el in root.xpath(P_REF_XPATH)
    )
    boundary_ulid_refs = tuple(
        RefState(elem=el, value=_safe_text(el.text)) for el in root.xpath(ULID_REF_XPATH)
    )

    return GeometryNumberingSnapshot(
        points=tuple(points),
        lines=tuple(lines),
        polyline_point_refs=polyline_point_refs,
        boundary_ulid_refs=boundary_ulid_refs,
    )


def _parse_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _analyze_id_list(values: list[str]) -> dict:
    parsed = []
    non_numeric = 0
    for v in values:
        i = _parse_int(v)
        if i is None:
            non_numeric += 1
        else:
            parsed.append(i)

    counts: dict[int, int] = {}
    for i in parsed:
        counts[i] = counts.get(i, 0) + 1
    duplicates = sorted([i for i, c in counts.items() if c > 1])

    positives = sorted([i for i in parsed if i > 0])
    missing = []
    if positives:
        max_id = positives[-1]
        present = set(positives)
        missing = sorted(set(range(1, max_id + 1)) - present)

    return {
        "count_total": len(values),
        "count_numeric": len(parsed),
        "count_non_numeric": non_numeric,
        "min": min(parsed) if parsed else None,
        "max": max(parsed) if parsed else None,
        "duplicates": duplicates,
        "missing": missing,
    }


def _format_id_analysis(title: str, values: Iterable[str]) -> str:
    values_list = list(values)
    info = _analyze_id_list(values_list)

    out = []
    out.append(f"{title}:")
    out.append(
        f"  - Всього: {len(values_list)}, числових: {info['count_numeric']}, нечислових/порожніх: {info['count_non_numeric']}"
    )
    out.append(f"  - Мін/Макс: {info['min']} / {info['max']}")

    dups = info["duplicates"][:50]
    miss = info["missing"][:50]
    out.append(
        f"  - Дублікати (перші 50): {', '.join(map(str, dups)) if dups else 'немає'}"
        + (f" (ще {len(info['duplicates']) - 50})" if len(info["duplicates"]) > 50 else "")
    )
    out.append(
        f"  - Пропуски 1..max (перші 50): {', '.join(map(str, miss)) if miss else 'немає'}"
        + (f" (ще {len(info['missing']) - 50})" if len(info["missing"]) > 50 else "")
    )
    return "\n".join(out)


def _format_configuration(snapshot: GeometryNumberingSnapshot, full: bool) -> str:
    out: list[str] = []

    out.append(_format_id_analysis("Вузли (PointInfo/Point) UIDP", (p.uidp for p in snapshot.points)))
    out.append(_format_id_analysis("Вузли (PointInfo/Point) PN", (p.pn for p in snapshot.points)))
    out.append(_format_id_analysis("Лінії (Polyline/PL) ULID", (l.ulid for l in snapshot.lines)))
    out.append("")

    uidps = {p.uidp for p in snapshot.points if p.uidp}
    ulids = {l.ulid for l in snapshot.lines if l.ulid}

    invalid_p_refs = [r.value for r in snapshot.polyline_point_refs if r.value and r.value not in uidps]
    invalid_ulid_refs = [r.value for r in snapshot.boundary_ulid_refs if r.value and r.value not in ulids]

    out.append("Посилання:")
    out.append(f"  - P (Polyline/PL/Points/P) всього: {len(snapshot.polyline_point_refs)}, некоректних: {len(invalid_p_refs)}")
    if invalid_p_refs:
        examples = ", ".join(invalid_p_refs[:30])
        out.append(f"    приклади (до 30): {examples}" + (f" (ще {len(invalid_p_refs) - 30})" if len(invalid_p_refs) > 30 else ""))
    out.append(f"  - ULID у контурах (Boundary/Lines/Line/ULID) всього: {len(snapshot.boundary_ulid_refs)}, некоректних: {len(invalid_ulid_refs)}")
    if invalid_ulid_refs:
        examples = ", ".join(invalid_ulid_refs[:30])
        out.append(f"    приклади (до 30): {examples}" + (f" (ще {len(invalid_ulid_refs) - 30})" if len(invalid_ulid_refs) > 30 else ""))

    if not full:
        return "\n".join(out)

    out.append("")
    out.append("Детально (повний перелік):")
    out.append("  Вузли (UIDP, PN, X, Y) у порядку в XML:")
    for p in snapshot.points:
        out.append(f"    - UIDP={p.uidp} PN={p.pn} X={p.x} Y={p.y}")

    out.append("  Лінії (ULID, точки) у порядку в XML:")
    for l in snapshot.lines:
        out.append(f"    - ULID={l.ulid} P=[{', '.join(l.point_refs)}]")

    return "\n".join(out)


def _format_algorithm() -> str:
    return "\n".join(
        [
            "Алгоритм перевірки/виправлення нумерації вузлів і ліній (виконується при відкритті):",
            "  1) Зібрати всі посилання на лінії ULID у контурах: Externals/Boundary/Lines, Internals/Boundary/Lines, AdjacentBoundary/Lines.",
            "  2) Видалити з <Polyline> всі <PL>, ULID яких ніде не використовується (\"висячі\" лінії).",
            "  3) Зібрати всі посилання на вузли UIDP у <Polyline>/<PL>/<Points>/<P> (для ліній, що залишились).",
            "  4) Видалити з <PointInfo> всі <Point>, UIDP яких ніде не використовується (\"висячі\" вузли).",
            "  5) Перенумерувати вузли: відсортувати <PointInfo>/<Point> за старим UIDP (як число) і присвоїти UIDP=1..N. (PN не перевіряється на унікальність і не виправляється.)",
            "  6) Оновити всі посилання <Polyline>/<PL>/<Points>/<P> згідно з мапою старий UIDP -> новий UIDP.",
            "  7) Перенумерувати лінії: відсортувати <Polyline>/<PL> за старим ULID (як число) і присвоїти ULID=1..M.",
            "  8) Оновити всі посилання на ULID у контурах згідно з мапою старий ULID -> новий ULID.",
        ]
    )


def build_geometry_numbering_report(
    *,
    xml_path: str,
    before: GeometryNumberingSnapshot,
    after: GeometryNumberingSnapshot,
) -> str:
    full_before_after = (len(before.points) + len(before.lines)) <= 2000

    removed_points = [p.uidp for p in before.points if getattr(p.elem, "getparent", lambda: None)() is None]
    removed_lines = [l.ulid for l in before.lines if getattr(l.elem, "getparent", lambda: None)() is None]

    uidp_map: list[tuple[str, str]] = []
    for p in before.points:
        if getattr(p.elem, "getparent", lambda: None)() is None:
            continue
        new_uidp = _safe_text(getattr(p.elem.find("UIDP"), "text", None))
        if p.uidp != new_uidp and p.uidp:
            uidp_map.append((p.uidp, new_uidp))

    ulid_map: list[tuple[str, str]] = []
    for l in before.lines:
        if getattr(l.elem, "getparent", lambda: None)() is None:
            continue
        new_ulid = _safe_text(getattr(l.elem.find("ULID"), "text", None))
        if l.ulid != new_ulid and l.ulid:
            ulid_map.append((l.ulid, new_ulid))

    changed_p_refs = 0
    for r in before.polyline_point_refs:
        new_val = _safe_text(getattr(r.elem, "text", None))
        if r.value != new_val:
            changed_p_refs += 1

    changed_ulid_refs = 0
    for r in before.boundary_ulid_refs:
        new_val = _safe_text(getattr(r.elem, "text", None))
        if r.value != new_val:
            changed_ulid_refs += 1

    out: list[str] = []
    out.append(f"Файл: {xml_path}")
    out.append(f"Дата/час: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    out.append("")
    out.append(_format_algorithm())
    out.append("")
    out.append("=== Вихідна конфігурація (до виправлення) ===")
    out.append(_format_configuration(before, full=full_before_after))
    out.append("")
    out.append("=== Причина змін / що саме було зроблено ===")
    out.append(f"- Видалено невикористовуваних ліній (PL): {len(removed_lines)}" + (f" (ULID: {', '.join(removed_lines[:50])}{' …' if len(removed_lines) > 50 else ''})" if removed_lines else ""))
    out.append(f"- Видалено невикористовуваних вузлів (Point): {len(removed_points)}" + (f" (UIDP: {', '.join(removed_points[:50])}{' …' if len(removed_points) > 50 else ''})" if removed_points else ""))
    out.append(f"- Перенумеровано UIDP: {len(uidp_map)} елемент(ів), оновлено посилань P: {changed_p_refs}")
    if uidp_map:
        out.append("  приклади UIDP (до 50): " + ", ".join(f"{a}->{b}" for a, b in uidp_map[:50]) + (f" (ще {len(uidp_map) - 50})" if len(uidp_map) > 50 else ""))
    out.append(f"- Перенумеровано ULID: {len(ulid_map)} елемент(ів), оновлено посилань ULID у контурах: {changed_ulid_refs}")
    if ulid_map:
        out.append("  приклади ULID (до 50): " + ", ".join(f"{a}->{b}" for a, b in ulid_map[:50]) + (f" (ще {len(ulid_map) - 50})" if len(ulid_map) > 50 else ""))
    out.append("")
    out.append("=== Змінена конфігурація (після виправлення) ===")
    out.append(_format_configuration(after, full=full_before_after))

    return "\n".join(out) + "\n"


def numbering_report_path(xml_path: str) -> str:
    p = Path(xml_path)
    return str(p.with_name(f"{p.stem}_нумерація.txt"))


def write_numbering_report(*, xml_path: str, report_text: str) -> str:
    report_path = numbering_report_path(xml_path)
    Path(report_path).write_text(report_text, encoding="utf-8")
    return report_path
