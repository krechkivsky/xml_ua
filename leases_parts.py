"""
leases_parts.py

Builds the table "Перелік частин ділянки переданих в оренду" for the cadastral plan layout.
"""

from __future__ import annotations

from typing import List, Tuple

from qgis.PyQt.QtGui import QFont, QFontMetricsF
from qgis.PyQt.QtWidgets import QApplication


class LeasesPartsTable:
    """
    HTML table for lease parts.

    Columns:
    - №: object_id of <LeaseInfo>
    - Площа: <LeaseAgreement/Area>
    - Орендар: list of Leasee (each in a new line)
    """

    HEADER_BG = "#f2f2f2"
    ALT_BG = "#f7f7f7"
    BORDER_MM = 0.1

    @staticmethod
    def _text_width_mm(font: QFont, text: str) -> float:
        try:
            from qgis.core import QgsLayoutUtils

            return float(QgsLayoutUtils.textWidthMM(font, str(text)))
        except Exception:
            try:
                fm = QFontMetricsF(font)
                px = float(fm.horizontalAdvance(str(text)))
                dpi = 96.0
                try:
                    scr = QApplication.primaryScreen()
                    if scr:
                        dpi = float(scr.logicalDotsPerInch() or 96.0)
                except Exception:
                    dpi = 96.0
                if dpi <= 0:
                    dpi = 96.0
                return px * 25.4 / dpi
            except Exception:
                try:
                    return float(len(str(text))) * 0.25
                except Exception:
                    return 0.0

    @staticmethod
    def _full_name(person_el) -> str:
        if person_el is None:
            return ""

        def _t(xpath_expr: str) -> str:
            try:
                res = person_el.xpath(xpath_expr)
                if res and getattr(res[0], "text", None):
                    return str(res[0].text).strip()
            except Exception:
                return ""
            try:
                el = person_el.find(xpath_expr)
                if el is not None and getattr(el, "text", None):
                    return str(el.text).strip()
            except Exception:
                return ""
            return ""

        txt = ""
        try:
            if getattr(person_el, "text", None):
                txt = str(person_el.text).strip()
        except Exception:
            txt = ""
        if txt:
            return txt

        parts = [
            _t(".//*[local-name()='LastName'][1]"),
            _t(".//*[local-name()='FirstName'][1]"),
            _t(".//*[local-name()='MiddleName'][1]"),
        ]
        return " ".join(p for p in parts if p)

    @staticmethod
    def _parse_leases(xml_root) -> List[Tuple[str, str, List[str]]]:
        """
        Returns list of (object_id, area_text, lessees_list).
        """
        if xml_root is None:
            return []

        try:
            infos = xml_root.xpath(
                "//*[local-name()='Leases']/*[local-name()='LeaseInfo']"
            )
        except Exception:
            try:
                infos = xml_root.findall(".//Leases/LeaseInfo")
            except Exception:
                infos = []

        rows: List[Tuple[str, str, List[str]]] = []
        for info in infos:
            try:
                obj_id = str(info.get("object_id") or "").strip()
            except Exception:
                obj_id = ""

            area_txt = ""
            try:
                el = info.xpath(".//*[local-name()='LeaseAgreement']/*[local-name()='Area'][1]")
                if el and getattr(el[0], "text", None):
                    area_txt = str(el[0].text).strip()
            except Exception:
                try:
                    el2 = info.find(".//LeaseAgreement/Area")
                    if el2 is not None and getattr(el2, "text", None):
                        area_txt = str(el2.text).strip()
                except Exception:
                    area_txt = ""

            lessees: List[str] = []
            try:
                leasees = info.xpath(
                    ".//*[local-name()='LeaseAgreement']/*[local-name()='Leasees']/*[local-name()='Leasee']"
                )
            except Exception:
                leasees = []
            for leasee in leasees:
                name = ""
                try:
                    legal = leasee.xpath(".//*[local-name()='LegalEntity']/*[local-name()='Name'][1]")
                    if legal and getattr(legal[0], "text", None):
                        name = str(legal[0].text).strip()
                except Exception:
                    name = ""

                if not name:
                    try:
                        np = leasee.xpath(".//*[local-name()='NaturalPerson']/*[local-name()='FullName'][1]")
                        if np:
                            name = LeasesPartsTable._full_name(np[0])
                    except Exception:
                        name = ""

                if name:
                    lessees.append(name)

            rows.append((obj_id, area_txt, lessees))

        def _k(r):
            try:
                return (0, int(r[0]))
            except Exception:
                return (1, r[0])

        rows.sort(key=_k)
        return rows

    @staticmethod
    def build_html(xml_root, font: QFont, body_row_h_mm: float, header_row_h_mm: float) -> Tuple[str, int, float]:
        """
        Returns (html, rows_count, table_width_mm).
        """
        items = LeasesPartsTable._parse_leases(xml_root)
        if not items:
            return "", 0, 0.0

        headers = ["№", "Площа", "Орендар"]

        # For width estimation: use the longest line in a multiline cell.
        lessee_width_samples: List[str] = [headers[2]]
        for _, _, names in items:
            parts = [str(p).strip() for p in (names or []) if str(p).strip()]
            lessee_width_samples.append(max(parts, key=len) if parts else "")

        cols = [
            [headers[0]] + [r[0] for r in items],
            [headers[1]] + [r[1] for r in items],
            lessee_width_samples,
        ]

        pad_mm = 4.0
        widths = [max(LeasesPartsTable._text_width_mm(font, t) for t in col) + pad_mm for col in cols]
        widths[0] = max(widths[0], 12.0)
        widths[1] = max(widths[1], 22.0)
        widths[2] = max(widths[2], 80.0)

        table_w_mm = float(sum(widths))

        def esc(s: str) -> str:
            return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        tr_head = f"height:{float(header_row_h_mm):.2f}mm;"
        tr_body = f"height:{float(body_row_h_mm):.2f}mm;"
        th_style = f"font-weight:normal; padding:0 2px; {tr_head} text-align:center;"
        td_style = f"text-align:left; padding:0 2px; {tr_body} white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"
        td_style_last = f"text-align:left; padding:0 2px; {tr_body} white-space:normal;"

        colgroup = "\n".join([f"<col style='width:{w:.2f}mm;'>" for w in widths])

        rows_html: List[str] = []
        rows_html.append(
            f"<tr style='background:{LeasesPartsTable.HEADER_BG}; {tr_head}'>"
            + "".join([f"<th style='{th_style}'>{esc(h)}</th>" for h in headers])
            + "</tr>"
        )

        for i, (obj_id, area_txt, lessees) in enumerate(items):
            bg = f"background:{LeasesPartsTable.ALT_BG};" if i % 2 == 1 else ""
            safe_names = [esc(str(n)) for n in (lessees or []) if str(n).strip()]
            lessees_html = "<br/>".join(safe_names)
            rows_html.append(
                f"<tr style='{bg} {tr_body}'>"
                f"<td style='{td_style}'>{esc(obj_id)}</td>"
                f"<td style='{td_style}'>{esc(area_txt)}</td>"
                f"<td style='{td_style_last}'>{lessees_html}</td>"
                "</tr>"
            )

        font_pt = float(font.pointSizeF() or 8.0)
        html = f"""
        <div style="width:{table_w_mm:.2f}mm; font-size:{font_pt:.2f}pt; font-weight:normal;">
          <table style="
            width:{table_w_mm:.2f}mm;
            table-layout:fixed;
            border-collapse:collapse;
            border:{LeasesPartsTable.BORDER_MM}mm solid #888;
          ">
            <colgroup>
              {colgroup}
            </colgroup>
            {''.join(rows_html)}
          </table>
        </div>
        """
        return html, len(items), table_w_mm
