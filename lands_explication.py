"""
lands_explication.py

Builds the "Експлікація угідь" table for the cadastral plan layout.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from qgis.PyQt.QtGui import QFont, QFontMetricsF
from qgis.PyQt.QtWidgets import QApplication

from .common import config


class LandsExplicationTable:
    """
    Creates an HTML table (QgsLayoutItemLabel.ModeHtml) for lands explication.

    Columns:
    - Номер: object_id attribute of <LandParcelInfo>
    - Площа: <MetricInfo><Area><Size>
    - Код: <LandCode>
    - Призначення: dictionary value from [LandsCode] by key==Код
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
    def _lands_code_dict() -> Dict[str, str]:
        try:
            if "LandsCode" in config:
                return dict(config["LandsCode"])
        except Exception:
            pass
        try:
            if "LandCodes" in config:
                return dict(config["LandCodes"])
        except Exception:
            pass
        return {}

    @staticmethod
    def _parse_land_parcels(xml_root) -> List[Tuple[str, str, str, str]]:
        """
        Returns (object_id, area_size, land_code, purpose_text).
        """
        if xml_root is None:
            return []

        lands_code_map = LandsExplicationTable._lands_code_dict()

        try:
            infos = xml_root.xpath(
                "//*[local-name()='LandsParcel']/*[local-name()='LandParcelInfo']"
            )
        except Exception:
            infos = []

        rows: List[Tuple[str, str, str, str]] = []
        for info in infos:
            try:
                obj_id = str(info.get("object_id") or "").strip()
            except Exception:
                obj_id = ""

            land_code = ""
            try:
                lc = info.xpath("./*[local-name()='LandCode'][1]")
                if lc and getattr(lc[0], "text", None):
                    land_code = str(lc[0].text).strip()
            except Exception:
                land_code = ""

            size = ""
            try:
                sz = info.xpath(
                    "./*[local-name()='MetricInfo'][1]/*[local-name()='Area'][1]/*[local-name()='Size'][1]"
                )
                if sz and getattr(sz[0], "text", None):
                    size = str(sz[0].text).strip()
            except Exception:
                size = ""

            purpose = lands_code_map.get(land_code, "")
            rows.append((obj_id, size, land_code, purpose))


        def _k(r):
            try:
                return (0, int(r[0]))
            except Exception:
                return (1, r[0])

        rows.sort(key=_k)
        return rows

    @staticmethod
    def build_html(
        xml_root,
        font: QFont,
        body_row_h_mm: float,
        header_row_h_mm: float,
    ) -> Tuple[str, int, float]:
        """
        Returns (html, rows_count, table_width_mm).
        """
        items = LandsExplicationTable._parse_land_parcels(xml_root)
        if not items:
            return "", 0, 0.0

        headers = ["Номер", "Площа", "Код", "Призначення"]


        cols = [
            [headers[0]] + [r[0] for r in items],
            [headers[1]] + [r[1] for r in items],
            [headers[2]] + [r[2] for r in items],
            [headers[3]] + [r[3] for r in items],
        ]
        pad_mm = 4.0
        widths = [max(LandsExplicationTable._text_width_mm(font, t) for t in col) + pad_mm for col in cols]


        widths[0] = max(widths[0], 12.0)
        widths[1] = max(widths[1], 18.0)
        widths[2] = max(widths[2], 16.0)
        widths[3] = max(widths[3], 50.0)

        table_w_mm = float(sum(widths))

        def esc(s: str) -> str:
            return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        tr_head = f"height:{float(header_row_h_mm):.2f}mm;"
        tr_body = f"height:{float(body_row_h_mm):.2f}mm;"
        th_style = f"font-weight:normal; padding:0 2px; {tr_head} text-align:center;"
        td_style = f"text-align:left; padding:0 2px; {tr_body} white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"

        colgroup = "\n".join([f"<col style='width:{w:.2f}mm;'>" for w in widths])

        rows_html: List[str] = []
        rows_html.append(
            f"<tr style='background:{LandsExplicationTable.HEADER_BG}; {tr_head}'>"
            + "".join([f"<th style='{th_style}'>{esc(h)}</th>" for h in headers])
            + "</tr>"
        )

        for i, (obj_id, size, land_code, purpose) in enumerate(items):
            bg = f"background:{LandsExplicationTable.ALT_BG};" if i % 2 == 1 else ""
            rows_html.append(
                f"<tr style='{bg} {tr_body}'>"
                f"<td style='{td_style}'>{esc(obj_id)}</td>"
                f"<td style='{td_style}'>{esc(size)}</td>"
                f"<td style='{td_style}'>{esc(land_code)}</td>"
                f"<td style='{td_style}'>{esc(purpose)}</td>"
                "</tr>"
            )

        font_pt = float(font.pointSizeF() or 8.0)
        html = f"""
        <div style="width:{table_w_mm:.2f}mm; font-size:{font_pt:.2f}pt; font-weight:normal;">
          <table style="
            width:{table_w_mm:.2f}mm;
            table-layout:fixed;
            border-collapse:collapse;
            border:{LandsExplicationTable.BORDER_MM}mm solid #888;
          ">
            <colgroup>
              {colgroup}
            </colgroup>
            {''.join(rows_html)}
          </table>
        </div>
        """
        return html, len(items), table_w_mm
