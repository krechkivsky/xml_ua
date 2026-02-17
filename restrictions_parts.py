"""
restrictions_parts.py

Builds the table "Перелік частин ділянки з обмеженнями" for the cadastral plan layout.
"""

from __future__ import annotations

import configparser
import os
from typing import Dict, List, Tuple

from qgis.PyQt.QtGui import QFont, QFontMetricsF
from qgis.PyQt.QtWidgets import QApplication


class RestrictionsPartsTable:
    """
    HTML table for restrictions parts.

    Columns:
    - Номер: object_id of <RestrictionInfo> (and corresponding layer feature)
    - Площа: geometry area (ha) of the restriction feature
    - Код: <RestrictionCode>
    - Зміст обмеження: dictionary value from [RestrictionCode] in templates/restriction.ini for the selected code
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
    def _restriction_code_dict() -> Dict[str, str]:
        path = os.path.join(os.path.dirname(__file__), "templates", "restriction.ini")
        cfg = configparser.ConfigParser()
        try:
            cfg.read(path, encoding="utf-8")
        except Exception:
            try:
                cfg.read(path)
            except Exception:
                return {}
        try:
            if "RestrictionCode" in cfg:
                return dict(cfg["RestrictionCode"])
        except Exception:
            return {}
        return {}

    @staticmethod
    def _area_ha_by_object_id(restrictions_layer) -> Dict[str, float]:
        """
        Builds object_id(str) -> area_ha(float).
        """
        out: Dict[str, float] = {}
        if restrictions_layer is None:
            return out
        try:
            for f in restrictions_layer.getFeatures():
                oid = ""
                try:
                    oid = str(f["object_id"]).strip()
                except Exception:
                    oid = ""
                if not oid:
                    continue
                try:
                    g = f.geometry()
                    if g is None or g.isEmpty():
                        continue
                    area_m2 = float(g.area())
                    out[oid] = area_m2 / 10000.0
                except Exception:
                    continue
        except Exception:
            return out
        return out

    @staticmethod
    def _parse_restrictions(xml_root, restrictions_layer) -> List[Tuple[str, str, str, str]]:
        """
        Returns (object_id, area_ha_str, restriction_code, restriction_name_text).
        """
        if xml_root is None:
            return []

        code_map = RestrictionsPartsTable._restriction_code_dict()
        area_by_oid = RestrictionsPartsTable._area_ha_by_object_id(restrictions_layer)

        try:
            infos = xml_root.xpath(
                "//*[local-name()='Restrictions']/*[local-name()='RestrictionInfo']"
            )
        except Exception:
            infos = []

        rows: List[Tuple[str, str, str, str]] = []
        for info in infos:
            try:
                obj_id = str(info.get("object_id") or "").strip()
            except Exception:
                obj_id = ""

            code = ""
            try:
                el = info.xpath("./*[local-name()='RestrictionCode'][1]")
                if el and getattr(el[0], "text", None):
                    code = str(el[0].text).strip()
            except Exception:
                code = ""

            name = code_map.get(code, "")
            area_ha = area_by_oid.get(obj_id)
            area_txt = f"{area_ha:.4f}" if isinstance(area_ha, (int, float)) else ""

            rows.append((obj_id, area_txt, code, name))

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
        restrictions_layer,
        font: QFont,
        body_row_h_mm: float,
        header_row_h_mm: float,
    ) -> Tuple[str, int, float]:
        """
        Returns (html, rows_count, table_width_mm).
        """
        items = RestrictionsPartsTable._parse_restrictions(xml_root, restrictions_layer)
        if not items:
            return "", 0, 0.0

        headers = ["Номер", "Площа, га", "Код", "Зміст обмеження"]

        cols = [
            [headers[0]] + [r[0] for r in items],
            [headers[1]] + [r[1] for r in items],
            [headers[2]] + [r[2] for r in items],
            [headers[3]] + [r[3] for r in items],
        ]
        pad_mm = 4.0
        widths = [max(RestrictionsPartsTable._text_width_mm(font, t) for t in col) + pad_mm for col in cols]

        widths[0] = max(widths[0], 12.0)
        widths[1] = max(widths[1], 22.0)
        widths[2] = max(widths[2], 16.0)
        widths[3] = max(widths[3], 60.0)

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
            f"<tr style='background:{RestrictionsPartsTable.HEADER_BG}; {tr_head}'>"
            + "".join([f"<th style='{th_style}'>{esc(h)}</th>" for h in headers])
            + "</tr>"
        )

        for i, (obj_id, area_txt, code, name) in enumerate(items):
            bg = f"background:{RestrictionsPartsTable.ALT_BG};" if i % 2 == 1 else ""
            rows_html.append(
                f"<tr style='{bg} {tr_body}'>"
                f"<td style='{td_style}'>{esc(obj_id)}</td>"
                f"<td style='{td_style}'>{esc(area_txt)}</td>"
                f"<td style='{td_style}'>{esc(code)}</td>"
                f"<td style='{td_style}'>{esc(name)}</td>"
                "</tr>"
            )

        font_pt = float(font.pointSizeF() or 8.0)
        html = f"""
        <div style="width:{table_w_mm:.2f}mm; font-size:{font_pt:.2f}pt; font-weight:normal;">
          <table style="
            width:{table_w_mm:.2f}mm;
            table-layout:fixed;
            border-collapse:collapse;
            border:{RestrictionsPartsTable.BORDER_MM}mm solid #888;
          ">
            <colgroup>
              {colgroup}
            </colgroup>
            {''.join(rows_html)}
          </table>
        </div>
        """
        return html, len(items), table_w_mm

