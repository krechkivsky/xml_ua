from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

def _parse_float(value, default=None):
    """
    Локальний парсер float для значень з XML.

    Не покладається на common.py, щоб перевірка працювала навіть при частковому reload модулів у QGIS.
    """
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default

    s = s.replace("\u00a0", " ").replace(" ", "")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return default


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _normalize_number_text_with_comma(value: str) -> str | None:
    if value is None:
        return None
    original = str(value)
    s = original.strip()
    if not s or "," not in s:
        return None

    s = s.replace("\u00a0", " ").replace(" ", "")
    allowed = set("0123456789-+.,")
    if any(ch not in allowed for ch in s):
        return None

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            normalized = s.replace(".", "").replace(",", ".")
        else:
            normalized = s.replace(",", "")
    else:
        normalized = s.replace(",", ".")

    if normalized == s:
        return None

    # Валідуємо, що результат дійсно можна інтерпретувати як число.
    try:
        float(normalized)
    except ValueError:
        return None
    return normalized


def _find_decimal_comma_numbers_in_tree(xml_tree, numeric_names=None, limit: int = 2000):
    if xml_tree is None:
        return []
    try:
        root = xml_tree.getroot()
    except Exception:
        return []
    if root is None:
        return []

    hits = []
    for el in root.xpath(".//*"):
        try:
            txt = el.text
        except Exception:
            continue
        if txt is None:
            continue
        if _normalize_number_text_with_comma(txt) is None:
            continue
        hits.append({"tag": getattr(el, "tag", ""), "text": str(txt)})
        if len(hits) >= int(limit):
            break
    return hits


def _normalize_decimal_commas_in_tree(xml_tree, numeric_names=None):
    if xml_tree is None:
        return []
    try:
        root = xml_tree.getroot()
    except Exception:
        return []
    if root is None:
        return []

    changes = []
    for el in root.xpath(".//*"):
        try:
            old = el.text
        except Exception:
            continue
        if old is None:
            continue
        new = _normalize_number_text_with_comma(old)
        if new is None:
            continue
        try:
            el.text = new
        except Exception:
            continue
        changes.append({"tag": getattr(el, "tag", ""), "old": str(old), "new": str(new)})
    return changes


def area_err_report_path(xml_path: str) -> str:
    p = Path(xml_path)
    return str(p.with_name(f"{p.stem}_area_err.txt"))


def write_area_err_report(*, xml_path: str, report_text: str) -> str:
    report_path = area_err_report_path(xml_path)
    Path(report_path).write_text(report_text, encoding="utf-8")
    return report_path


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LandAreaMismatch:
    idx: int
    cadastral_code: str
    land_code: str
    old_text: str
    old_value_ha: float | None
    computed_ha: float
    new_text: str


@dataclass(frozen=True)
class AreaChecksResult:
    comma_hits_count: int
    comma_fixed_count: int
    comma_examples: tuple[str, ...]

    parcel_area_xml_text: str
    parcel_area_xml_ha: float | None
    parcel_area_computed_ha: float | None
    parcel_area_fixed: bool
    parcel_area_new_text: str

    lands_checked: int
    lands_fixed: int
    land_mismatches: tuple[LandAreaMismatch, ...]

    lands_sum_computed_q4_ha: Decimal | None
    balance_ref_parcel_q4_ha: Decimal | None
    balance_diff_q4_ha: Decimal | None

    changes_made: bool
    any_issue: bool


def _ring_area_m2(coords: list[tuple[float, float]]) -> float:
    if len(coords) < 3:
        return 0.0
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    area = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) / 2.0


def _chain_lines_to_ring(ulids: Iterable[str], ulid_to_coords: dict[str, list[tuple[float, float]]]) -> list[tuple[float, float]] | None:
    ulids = [u for u in ulids if u in ulid_to_coords]
    if not ulids:
        return None

    used = set()
    first = ulids[0]
    ring = list(ulid_to_coords[first])
    used.add(first)

    while len(used) < len(ulids):
        last = ring[-1]
        progressed = False
        for u in ulids:
            if u in used:
                continue
            coords = ulid_to_coords.get(u)
            if not coords:
                continue
            if coords[0] == last:
                ring.extend(coords[1:])
                used.add(u)
                progressed = True
                break
            if coords[-1] == last:
                ring.extend(list(reversed(coords[:-1])))
                used.add(u)
                progressed = True
                break
        if not progressed:
            return None

    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def run_area_checks_and_fix_tree(
    *,
    xml_tree,
    parcel_area_computer,
    threshold_round_digits: int = 4,
) -> AreaChecksResult:
    """
    Виконує 4 перевірки:
    1) десяткова кома в числових полях (виправляється в дереві),
    2) площа ділянки XML vs обчислена (виправляється в дереві),
    3) площі угідь XML vs обчислені (виправляються в дереві),
    4) юридичний баланс: сума площ угідь (обчислених, q4) vs площа ділянки з XML (початково, q4).

    Повертає результати і прапорці.
    """
    root = xml_tree.getroot() if xml_tree is not None else None

    # Початковий текст площі ділянки з XML (для балансу)
    try:
        parcel_area_text_initial = (
            xml_tree.xpath(
                "string(//*[local-name()='ParcelMetricInfo']/*[local-name()='Area']/*[local-name()='Size'][1])"
            )
            or ""
        ).strip()
    except Exception:
        parcel_area_text_initial = ""

    # 1) Десяткова кома
    comma_hits = _find_decimal_comma_numbers_in_tree(xml_tree)
    comma_examples = []
    for h in comma_hits[:5]:
        comma_examples.append(f"<{h.get('tag', '')}>: '{h.get('text', '')}'")
    comma_fixed = _normalize_decimal_commas_in_tree(xml_tree) if comma_hits else []

    # 2) Площа ділянки
    parcel_area_xml_ha = _parse_float(parcel_area_text_initial, default=None)
    parcel_area_computed_ha = parcel_area_computer(xml_tree)
    parcel_area_fixed = False
    parcel_area_new_text = ""
    if parcel_area_computed_ha is not None:
        parcel_area_new_text = f"{parcel_area_computed_ha:.{threshold_round_digits}f}"
        if parcel_area_xml_ha is None:
            parcel_area_fixed = False
        else:
            if round(parcel_area_xml_ha, threshold_round_digits) != round(parcel_area_computed_ha, threshold_round_digits):
                # Оновлюємо всі ParcelMetricInfo/Area/Size незалежно від namespace
                try:
                    for size_el in xml_tree.xpath(
                        "//*[local-name()='ParcelMetricInfo']/*[local-name()='Area']/*[local-name()='Size']"
                    ):
                        try:
                            size_el.text = parcel_area_new_text
                        except Exception:
                            pass
                    parcel_area_fixed = True
                except Exception:
                    parcel_area_fixed = False

    # 3) Площі угідь: обчислення за лініями/вузлами
    lands_checked = 0
    lands_fixed = 0
    mismatches: list[LandAreaMismatch] = []

    lands_sum_computed_q4 = Decimal("0.0")
    lands_sum_computed_valid = True

    if root is not None:
        # UIDP -> (X, Y)
        uidp_to_xy: dict[str, tuple[float, float]] = {}
        for point in root.xpath(".//*[local-name()='PointInfo']/*[local-name()='Point']"):
            uidp = (point.xpath("string(./*[local-name()='UIDP'][1])") or "").strip()
            if not uidp:
                continue
            x_text = (point.xpath("string(./*[local-name()='X'][1])") or "").strip()
            y_text = (point.xpath("string(./*[local-name()='Y'][1])") or "").strip()
            x_val = _parse_float(x_text, default=None)
            y_val = _parse_float(y_text, default=None)
            if x_val is None or y_val is None:
                continue
            uidp_to_xy[uidp] = (x_val, y_val)

        # ULID -> coords (по PL/Points/P -> UIDP -> (X,Y))
        ulid_to_coords: dict[str, list[tuple[float, float]]] = {}
        for pl in root.xpath(".//*[local-name()='Polyline']/*[local-name()='PL']"):
            ulid = (pl.xpath("string(./*[local-name()='ULID'][1])") or "").strip()
            if not ulid:
                continue
            uidps = [
                str(t).strip()
                for t in pl.xpath("./*[local-name()='Points']/*[local-name()='P']/text()")
                if str(t).strip()
            ]
            coords: list[tuple[float, float]] = []
            ok = True
            for u in uidps:
                xy = uidp_to_xy.get(u)
                if not xy:
                    ok = False
                    break
                coords.append(xy)
            if ok and len(coords) >= 2:
                ulid_to_coords[ulid] = coords

        lands_infos = root.xpath(".//*[local-name()='LandsParcel']/*[local-name()='LandParcelInfo']")
        for i, land_info in enumerate(lands_infos, 1):
            metric_info = None
            for ch in land_info:
                if _local_name(getattr(ch, "tag", "")) == "MetricInfo":
                    metric_info = ch
                    break
            if metric_info is None:
                continue

            externals = metric_info.xpath(".//*[local-name()='Externals'][1]")
            if not externals:
                continue
            externals = externals[0]

            ext_lines = externals.xpath("./*[local-name()='Boundary']/*[local-name()='Lines'][1]")
            if not ext_lines:
                continue
            ext_ulids = [
                str(t).strip()
                for t in ext_lines[0].xpath("./*[local-name()='Line']/*[local-name()='ULID']/text()")
                if str(t).strip()
            ]
            ext_ring = _chain_lines_to_ring(ext_ulids, ulid_to_coords)
            if not ext_ring:
                continue

            area_m2 = _ring_area_m2(ext_ring)

            internals = externals.xpath("./*[local-name()='Internals']/*[local-name()='Boundary']")
            for b in internals:
                b_lines = b.xpath("./*[local-name()='Lines'][1]")
                if not b_lines:
                    continue
                b_ulids = [
                    str(t).strip()
                    for t in b_lines[0].xpath("./*[local-name()='Line']/*[local-name()='ULID']/text()")
                    if str(t).strip()
                ]
                hole_ring = _chain_lines_to_ring(b_ulids, ulid_to_coords)
                if hole_ring:
                    area_m2 -= _ring_area_m2(hole_ring)

            if area_m2 < 0:
                area_m2 = abs(area_m2)
            computed_ha = area_m2 / 10000.0

            lands_checked += 1

            updated_any = False
            old_text_for_report = ""
            old_val_for_report: float | None = None
            new_text_for_report = f"{computed_ha:.{threshold_round_digits}f}"

            # В XSD: MetricInfo/Area може бути unbounded.
            for area_el in metric_info.xpath("./*[local-name()='Area']"):
                unit = (area_el.xpath("string(./*[local-name()='MeasurementUnit'][1])") or "").strip()
                size_el = area_el.xpath("./*[local-name()='Size'][1]")
                if not size_el:
                    continue
                size_el = size_el[0]

                old_text = (size_el.text or "").strip()
                if not old_text_for_report:
                    old_text_for_report = old_text
                    old_val_for_report = _parse_float(old_text, default=None) if old_text else None

                if unit == "кв.м":
                    new_val = area_m2
                    new_text = f"{new_val:.{threshold_round_digits}f}"
                else:
                    new_val = computed_ha
                    new_text = f"{new_val:.{threshold_round_digits}f}"

                old_val = _parse_float(old_text, default=None) if old_text else None
                same = False
                if old_val is not None:
                    same = (round(float(old_val), threshold_round_digits) == round(float(new_val), threshold_round_digits))

                if not same:
                    try:
                        size_el.text = new_text
                        updated_any = True
                    except Exception:
                        pass

            if updated_any:
                lands_fixed += 1
                cadastral_code = (land_info.xpath("string(./*[local-name()='CadastralCode'][1])") or "").strip()
                land_code = (land_info.xpath("string(./*[local-name()='LandCode'][1])") or "").strip()
                mismatches.append(
                    LandAreaMismatch(
                        idx=i,
                        cadastral_code=cadastral_code,
                        land_code=land_code,
                        old_text=old_text_for_report,
                        old_value_ha=old_val_for_report,
                        computed_ha=float(computed_ha),
                        new_text=new_text_for_report,
                    )
                )

            try:
                lands_sum_computed_q4 += _q4(Decimal(str(round(computed_ha, threshold_round_digits))))
            except Exception:
                lands_sum_computed_valid = False

    # 4) Баланс
    balance_ref_parcel_q4 = None
    balance_diff_q4 = None
    if parcel_area_xml_ha is not None and lands_sum_computed_valid:
        try:
            balance_ref_parcel_q4 = _q4(Decimal(str(round(parcel_area_xml_ha, threshold_round_digits))))
            balance_diff_q4 = lands_sum_computed_q4 - balance_ref_parcel_q4
        except Exception:
            balance_ref_parcel_q4 = None
            balance_diff_q4 = None

    changes_made = bool(comma_hits) or parcel_area_fixed or lands_fixed > 0
    any_issue = bool(comma_hits) or parcel_area_fixed or lands_fixed > 0 or (
        balance_diff_q4 is not None and balance_diff_q4 != Decimal("0.0000")
    )

    return AreaChecksResult(
        comma_hits_count=len(comma_hits),
        comma_fixed_count=len(comma_fixed),
        comma_examples=tuple(comma_examples),
        parcel_area_xml_text=parcel_area_text_initial,
        parcel_area_xml_ha=parcel_area_xml_ha,
        parcel_area_computed_ha=parcel_area_computed_ha,
        parcel_area_fixed=parcel_area_fixed,
        parcel_area_new_text=parcel_area_new_text,
        lands_checked=lands_checked,
        lands_fixed=lands_fixed,
        land_mismatches=tuple(mismatches),
        lands_sum_computed_q4_ha=lands_sum_computed_q4 if lands_sum_computed_valid else None,
        balance_ref_parcel_q4_ha=balance_ref_parcel_q4,
        balance_diff_q4_ha=balance_diff_q4,
        changes_made=changes_made,
        any_issue=any_issue,
    )


def build_area_err_report(*, xml_path: str, result: AreaChecksResult) -> str:
    out: list[str] = []
    out.append(f"Файл: {xml_path}")
    out.append(f"Дата/час: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    out.append("")

    out.append("1) Десяткова кома замість крапки")
    if result.comma_hits_count == 0:
        out.append("  - Не виявлено.")
    else:
        out.append(f"  - Виявлено: {result.comma_hits_count}")
        out.append(f"  - Виправлено в дереві: {result.comma_fixed_count}")
        if result.comma_examples:
            out.append("  - Приклади:")
            for ex in result.comma_examples:
                out.append(f"    {ex}")
    out.append("")

    out.append("2) Площа ділянки: обчислена vs XML (q4)")
    if result.parcel_area_computed_ha is None:
        out.append("  - Не вдалося обчислити площу ділянки за геометрією.")
    else:
        out.append(f"  - XML: '{result.parcel_area_xml_text or 'N/A'}'")
        out.append(f"  - Обчислена: {result.parcel_area_computed_ha:.4f}")
        if result.parcel_area_fixed:
            out.append(f"  - Виправлено в дереві XML до: {result.parcel_area_new_text}")
        else:
            out.append("  - Змін не внесено.")
    out.append("")

    out.append("3) Площі угідь: обчислені vs XML (q4)")
    if result.lands_checked == 0:
        out.append("  - Угідь не знайдено або немає геометрії для обчислення.")
    else:
        out.append(f"  - Перевірено: {result.lands_checked}")
        out.append(f"  - Виправлено в дереві: {result.lands_fixed}")
        if result.land_mismatches:
            out.append("  - Деталі (виправлені):")
            for m in result.land_mismatches:
                out.append(
                    f"    {m.idx}. Угіддя код={m.land_code or 'N/A'} CadastralCode={m.cadastral_code or 'N/A'}: "
                    f"{m.old_text or 'N/A'} -> {m.new_text} (обчисл.: {m.computed_ha:.4f})"
                )
    out.append("")

    out.append("4) Юридичний баланс площ (q4)")
    if result.lands_sum_computed_q4_ha is None or result.balance_ref_parcel_q4_ha is None or result.balance_diff_q4_ha is None:
        out.append("  - Не вдалося обчислити баланс (немає даних для порівняння).")
    else:
        out.append(f"  - Сума угідь (обчислена, q4): {result.lands_sum_computed_q4_ha}")
        out.append(f"  - Площа ділянки з XML (початково, q4): {result.balance_ref_parcel_q4_ha}")
        out.append(f"  - Різниця: {result.balance_diff_q4_ha}")
        if result.balance_diff_q4_ha == Decimal('0.0000'):
            out.append("  - Баланс сходиться.")
        else:
            out.append("  - Баланс НЕ сходиться.")

    return "\n".join(out) + "\n"
