


"""
plan_layout.py

Формування кадастрового плану у QGIS Layout.

Ключові принципи (стабільно для друку/PDF):
- Підписи довжин ребер: ТІЛЬКИ стилем шару на Canvas (Layout їх НЕ створює)
  (інакше при друці можуть "вирівнюватися" в горизонталь).
- Літери суміжників: створюються в Layout, горизонтальні (rotation=0).
- Title (кадастровий номер) і "Масштаб 1:XXXX" — у Layout поверх карти, з фіксованою шириною.

Версія: 2026-02-09 (scale-choice + overlay labels)
"""

import math
import os
import configparser
from typing import Dict, Optional, Tuple

from qgis.core import (
    QgsProject,
    QgsPrintLayout,
    QgsLayoutItemMap,
    QgsLayoutItemLabel,
    QgsLayoutItemShape,
    QgsLayoutSize,
    QgsLayoutPoint,
    QgsUnitTypes,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsFillSymbol,
    QgsRectangle,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
)

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtGui import QFontMetricsF
from qgis.PyQt.QtWidgets import QApplication

from .common import PARCEL_MARGIN_FACTOR, log_calls, log_msg, logFile
from .symbols import Symbols
from .cases import to_genitive
from .lands_explication import LandsExplicationTable
from .restrictions_parts import RestrictionsPartsTable
from .leases_parts import LeasesPartsTable
from .subleases_parts import SubleasesPartsTable

LOG = True




PAGE_W_MM = 210.0
PAGE_H_MM = 297.0

MARGIN_LEFT_MM = 20.0
MARGIN_TOP_MM = 10.0
MARGIN_RIGHT_MM = 10.0
MARGIN_BOTTOM_MM = 10.0


MAP_SIDE_MM = 180.0


OVERLAY_PAD_MM = 2.0
TITLE_H_MM = 8.0
SCALE_H_MM = 6.0

NEIGHBOR_FONT_PT = 8

BOUNDARY_DESC_WIDTH_MM = 80.0
BOUNDARY_DESC_LINE_HEIGHT_MM = 4.0  # для font 8 pt
BOUNDARY_DESC_OFFSET_X_MM = 120.0


NODES_TABLE_X_MM = 20.0
NODES_TABLE_Y_MM = MARGIN_TOP_MM + MAP_SIDE_MM  # 10 + 180 = 190 мм


NODES_TABLE_COL_UIDP_MM = 10.0    # "№"
NODES_TABLE_COL_X_MM = 30.0       # X
NODES_TABLE_COL_Y_MM = 30.0       # Y
NODES_TABLE_COL_DESC_MM = 20.0    # "Опис"



NODES_TABLE_W_MM = 101.0

NODES_TABLE_BORDER_MM = 0.1
NODES_TABLE_FONT_PT = 8


NODES_TABLE_HEADER_BG = "#f2f2f2"
NODES_TABLE_ROW_ALT_BG = "#f7f7f7"
N_SPACES_XY = 10  # кількість нерозривних пробілів перед X і Y



NODES_TABLE_ROW_H_MM = 4.0
NODES_TABLE_HEADER_ROW_H_MM = 6.0
NODES_TABLE_TITLE_H_MM = 6.0


BOUNDARY_DESC_X_MM = 110.0
BOUNDARY_DESC_Y_MM = 190.0


SC63_TO_USC2000_EPSG = {
    "X": "EPSG:5562",
    "C": "EPSG:5563",
    "P": "EPSG:5564",
    "T": "EPSG:5565",
}


def _unit(vx: float, vy: float) -> Tuple[float, float]:
    L = math.hypot(vx, vy)
    if L == 0:
        return 0.0, 0.0
    return vx / L, vy / L


def compute_map_scale(extent: QgsRectangle, map_side_mm: float, margin_factor: float = PARCEL_MARGIN_FACTOR) -> int:
    """
    Обчислює масштаб 1:XXXX так, щоб квадратний extent (із запасом margin_factor)
    вміщався у квадрат карти map_side_mm (мм).

    ВАЖЛИВО: extent має бути в метричному CRS (метри).
    """
    extent_side = max(extent.width(), extent.height()) * float(margin_factor)
    scale = extent_side * 1000.0 / float(map_side_mm)  # map_side_mm мм = map_side_mm/1000 м
    return int(round(scale))


class PlanLayoutCreator:
    def __init__(self, iface, parent_group: QgsLayerTreeGroup, project: QgsProject, plugin=None):
        if LOG:
            log_calls(logFile, f"PlanLayoutCreator init: {parent_group.name()}")
        self.iface = iface
        self.project = project
        self.parent_group = parent_group
        self.plugin = plugin
        self.cadastral_plan_group = parent_group.findGroup("Кадастровий план")




    def _find_layer_exact(self, group, name: str):
        if not group:
            return None
        for ch in group.children():
            if isinstance(ch, QgsLayerTreeLayer):
                lyr = ch.layer()
                if lyr and lyr.name().lower() == name.lower():
                    return lyr
            if isinstance(ch, QgsLayerTreeGroup):
                r = self._find_layer_exact(ch, name)
                if r:
                    return r
        return None

    def _group_extent(self) -> Optional[QgsRectangle]:
        if not self.cadastral_plan_group:
            return None
        extent = None
        for ch in self.cadastral_plan_group.children():
            if isinstance(ch, QgsLayerTreeLayer):
                lyr = ch.layer()
                if not lyr:
                    continue
                extent = lyr.extent() if extent is None else extent.combineExtentWith(lyr.extent())
        return extent

    def _get_parcel_nodes_layer(self):
        """
        Повертає шар 'Вузли ділянки' з підгрупи 'Кадастровий план'
        """
        if not self.cadastral_plan_group:
            return None

        for ch in self.cadastral_plan_group.children():
            if isinstance(ch, QgsLayerTreeLayer):
                lyr = ch.layer()
                if lyr and lyr.name() == "Вузли ділянки":
                    return lyr
        return None



    def _map_xy_to_layout_mm(self, map_item: QgsLayoutItemMap, x: float, y: float) -> Tuple[float, float]:
        ext = map_item.extent()
        fx = (x - ext.xMinimum()) / ext.width()
        fy = (ext.yMaximum() - y) / ext.height()
        r = map_item.rect()
        p = map_item.positionWithUnits()
        return p.x() + fx * r.width(), p.y() + fy * r.height()

    def _page_y_offset(self, layout, page_idx: int) -> float:
        """
        Y offset for a 1-based page index in the layout coordinate system.

        QGIS layouts can have page spacing (typically 10 mm). If pageSpacing() is unavailable or returns
        <= 0, use 10 mm as a safe default so items on page 2+ don't appear 10 mm too high.
        """
        spacing = 10.0
        try:
            spacing = float(layout.pageCollection().pageSpacing())
        except Exception:
            spacing = 10.0
        if spacing <= 0:
            spacing = 10.0
        return float(page_idx - 1) * (float(PAGE_H_MM) + spacing)




    def _build_cadastral_title(self) -> str:
        """
        Формує:
        'Кадастровий план земельної ділянки ЗЗЗЗЗЗЗЗЗЗ:ЗЗ:ККК:ДДДД'
        Де DDDD -> '____' якщо пусто або '0000'.
        """
        base = "Кадастровий план земельної ділянки"

        if not self.plugin or not getattr(self.plugin, "dockwidget", None):
            return base

        try:

            group_name = self.parent_group.name()
            xml_data = self.plugin.dockwidget.get_xml_data_for_group(group_name)
            if not xml_data or not getattr(xml_data, "tree", None):
                return base

            root = xml_data.tree.getroot()


            def _first_text(xpath_expr: str) -> str:
                res = root.xpath(xpath_expr)
                if not res:
                    return ""
                node = res[0]
                txt = getattr(node, "text", "") or ""
                return txt.strip()

            zone = _first_text("//*[local-name()='CadastralZoneNumber'][1]")
            quarter = _first_text("//*[local-name()='CadastralQuarterNumber'][1]")
            parcel = _first_text("//*[local-name()='ParcelID'][1]")

            if parcel in ("", "0000"):
                parcel = "____"


            if zone and quarter:
                return f"{base} {zone}:{quarter}:{parcel}"

            if zone:
                return f"{base} {zone}::{parcel}"
            return base

        except Exception as e:
            log_msg(logFile, f"Title build error: {e}")
            return base

    def _xml_first_text(self, root, xpath_expr: str) -> str:
        try:
            if root is None:
                return ""
            res = root.xpath(xpath_expr)
            if not res:
                return ""
            node = res[0]
            txt = getattr(node, "text", "") or ""
            return str(txt).strip()
        except Exception:
            return ""

    def _ini_section_map(self, section: str) -> Dict[str, str]:
        try:
            if not hasattr(self, "_ini_cache"):
                self._ini_cache = {}
            if section in self._ini_cache:
                return self._ini_cache[section]

            ini_path = os.path.join(os.path.dirname(__file__), "templates", "xml_ua.ini")
            cfg = configparser.ConfigParser()
            cfg.optionxform = str
            cfg.read(ini_path, encoding="utf-8")
            m = dict(cfg[section]) if cfg.has_section(section) else {}
            self._ini_cache[section] = m
            return m
        except Exception:
            return {}

    def _xml_full_name(self, element) -> str:
        if element is None:
            return ""
        last_name = self._xml_first_text(element, "./*[local-name()='LastName'][1]")
        first_name = self._xml_first_text(element, "./*[local-name()='FirstName'][1]")
        middle_name = self._xml_first_text(element, "./*[local-name()='MiddleName'][1]")
        return " ".join([p for p in (last_name, first_name, middle_name) if p]).strip()

    def _build_parcel_location_formatted(self, root) -> str:
        """
        Builds a human-readable location string for ParcelLocationInfo, similar to documents.py.
        Includes [в межах]/[за межами] and uses address structure if present.
        """
        if root is None:
            return ""

        try:
            loc_infos = root.xpath("//*[local-name()='ParcelLocationInfo'][1]")
            if not loc_infos:
                return ""
            loc_info = loc_infos[0]

            region = self._xml_first_text(loc_info, "./*[local-name()='Region'][1]")
            district = self._xml_first_text(loc_info, "./*[local-name()='District'][1]")
            settlement = self._xml_first_text(loc_info, "./*[local-name()='Settlement'][1]")
            street = self._xml_first_text(loc_info, "./*[local-name()='ParcelAddress']/*[local-name()='StreetName'][1]")
            building = self._xml_first_text(loc_info, "./*[local-name()='ParcelAddress']/*[local-name()='Building'][1]")


            location_node = loc_info.xpath("./*[local-name()='ParcelLocation'][1]")
            location_node = location_node[0] if location_node else None
            is_urban = bool(location_node is not None and location_node.xpath("./*[local-name()='Urban']"))
            is_rural = bool(location_node is not None and location_node.xpath("./*[local-name()='Rural']"))

            if is_urban:
                base = "у межах населеного пункту"
                if settlement:
                    base = f"{base} {settlement}"

                addr_parts = []
                if any([region, district, street, building]):
                    addr_parts = [
                        f"за адресою: {region}, " if region else "за адресою: ",
                        f"{district} район," if district else "",
                        f"с. {settlement}," if settlement else "",
                        f"вул. {street}" if street else "",
                        f"№ {building}" if building else "",
                    ]
                addr = " ".join([p for p in addr_parts if p]).strip()
                return f"{base}{', ' + addr if addr else ''}".strip()

            if is_rural:
                region_g = to_genitive(region) if region else ""
                district_g = to_genitive(district) if district else ""
                settlement_g = to_genitive(settlement) if settlement else ""
                parts = [
                    f"за межами населеного пункту {settlement_g}" if settlement_g else "за межами населеного пункту",
                    f"{district_g} району" if district_g else "",
                    f"{region_g}" if region_g else "",
                ]
                return " ".join([p for p in parts if p]).strip()

            return ""
        except Exception:
            return ""

    def _build_customer_name(self, root) -> str:
        if root is None:
            return ""
        try:
            proprietors = root.xpath(
                "//*[local-name()='ParcelInfo']"
                "/*[local-name()='Proprietors']"
                "/*[local-name()='ProprietorInfo']"
            )
            owners = []
            for prop in proprietors:
                natural = prop.xpath(
                    ".//*[local-name()='Authentication']"
                    "/*[local-name()='NaturalPerson']"
                    "/*[local-name()='FullName'][1]"
                )
                legal = prop.xpath(
                    ".//*[local-name()='Authentication']"
                    "/*[local-name()='LegalEntity']"
                    "/*[local-name()='Name'][1]/text()"
                )
                if natural:
                    nm = self._xml_full_name(natural[0])
                    if nm:
                        owners.append(nm)
                elif legal:
                    nm = str(legal[0]).strip()
                    if nm:
                        owners.append(nm)
            return ", ".join([o for o in owners if o]).strip()
        except Exception:
            return ""

    def _build_executor_company(self, root) -> str:
        if root is None:
            return ""
        try:
            res = root.xpath(
                "/*[local-name()='UkrainianCadastralExchangeFile']"
                "/*[local-name()='AdditionalPart']"
                "/*[local-name()='InfoLandWork']"
                "/*[local-name()='Executor']"
                "/*[local-name()='CompanyName'][1]/text()"
            )
            return str(res[0]).strip() if res else ""
        except Exception:
            return ""

    def _build_cadastral_number(self, root) -> str:
        zone = self._xml_first_text(root, "//*[local-name()='CadastralZoneNumber'][1]")
        quarter = self._xml_first_text(root, "//*[local-name()='CadastralQuarterNumber'][1]")
        parcel = self._xml_first_text(root, "//*[local-name()='ParcelID'][1]")
        if parcel in ("", "0000"):
            parcel = "____"
        if zone and quarter:
            return f"{zone}:{quarter}:{parcel}"
        if zone:
            return f"{zone}::{parcel}"
        return ""

    def _build_executor_fio(self, root) -> str:
        base = (
            "/*[local-name()='UkrainianCadastralExchangeFile']"
            "/*[local-name()='AdditionalPart']"
            "/*[local-name()='InfoLandWork']"
            "/*[local-name()='Executor']"
            "/*[local-name()='Executor'][1]"
            "/*[local-name()='ExecutorName']"
        )
        last_name = self._xml_first_text(root, f"{base}/*[local-name()='LastName'][1]")
        first_name = self._xml_first_text(root, f"{base}/*[local-name()='FirstName'][1]")
        middle_name = self._xml_first_text(root, f"{base}/*[local-name()='MiddleName'][1]")
        fio = " ".join([p for p in (last_name, first_name, middle_name) if p])
        return fio.strip()

    def _build_executor_signature_name(self, root) -> str:
        base = (
            "/*[local-name()='UkrainianCadastralExchangeFile']"
            "/*[local-name()='AdditionalPart']"
            "/*[local-name()='InfoLandWork']"
            "/*[local-name()='Executor']"
            "/*[local-name()='Executor'][1]"
            "/*[local-name()='ExecutorName']"
        )
        last_name = self._xml_first_text(root, f"{base}/*[local-name()='LastName'][1]")
        first_name = self._xml_first_text(root, f"{base}/*[local-name()='FirstName'][1]")
        middle_name = self._xml_first_text(root, f"{base}/*[local-name()='MiddleName'][1]")

        first_initial = (first_name[:1] + ".") if first_name else ""
        middle_initial = (middle_name[:1] + ".") if middle_name else ""
        tail = " ".join([p for p in (last_name, first_initial, middle_initial) if p]).strip()
        return tail

    def _xml_get_sc63_zone(self):
        """
        Повертає 'X', 'C', 'P' або 'T' для:
        <SC63><X/></SC63>
        з namespace або без нього.
        """

        plugin = self.plugin
        if not plugin or not plugin.dockwidget:
            return None

        xml_data = None
        for xd in plugin.dockwidget.opened_xmls:
            if xd.group_name == self.parent_group.name():
                xml_data = xd
                break

        if not xml_data or not xml_data.tree:
            return None

        root = xml_data.tree.getroot()

        base = (
            "/*[local-name()='UkrainianCadastralExchangeFile']"
            "/*[local-name()='InfoPart']"
            "/*[local-name()='MetricInfo']"
            "/*[local-name()='CoordinateSystem']"
            "/*[local-name()='SC63']"
        )

        for z in ("X", "C", "P", "T"):
            if root.xpath(f"{base}/*[local-name()='{z}']"):
                if LOG:
                    log_msg(logFile, f"_xml_get_sc63_zone(): detected zone = {z}")
                return z

        return None



    def _build_nodes_table_html(self, font_pt: Optional[float] = None) -> Tuple[str, int]:
        """
        Формує HTML-таблицю координат з шару 'Вузли ділянки'
        """
        SP = "\u00A0"

        nodes_layer = self._get_parcel_nodes_layer()
        if not nodes_layer:
            return "", 0






        sc63_zone = self._xml_get_sc63_zone()
        if LOG: log_msg(logFile, f"sc63_zone {sc63_zone}")

        transform = None
        if sc63_zone:
            epsg = SC63_TO_USC2000_EPSG.get(sc63_zone)
            if epsg:
                crs_dst = QgsCoordinateReferenceSystem(epsg)
                crs_src = nodes_layer.crs()
                if crs_src.isValid() and crs_dst.isValid():
                    transform = QgsCoordinateTransform(
                        crs_src, crs_dst, QgsProject.instance()
                    )






        fld_uidp = "UIDP" if "UIDP" in [f.name() for f in nodes_layer.fields()] else None
        if not fld_uidp:
            return "", 0

        def esc(s: str) -> str:
            return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        def fmt(v: float) -> str:
            try:
                return f"{float(v):.2f}"
            except Exception:
                return ""















        rows = []

        for f in nodes_layer.getFeatures():
            pt = f.geometry().asPoint()
            uidp = str(f["UIDP"]).strip()

            row = {
                "uidp": uidp,
                "x": pt.x(),
                "y": pt.y(),
            }

            if transform:
                pt2 = transform.transform(pt)
                row["x2"] = pt2.x()
                row["y2"] = pt2.y()

            rows.append(row)




        def uidp_key(d):
            try:
                return int(d["uidp"])
            except Exception:
                return 10**12

        rows.sort(key=uidp_key)


        font_pt = float(font_pt) if font_pt else float(NODES_TABLE_FONT_PT)
        body_row_h = float(NODES_TABLE_ROW_H_MM)
        header_row_h = float(NODES_TABLE_HEADER_ROW_H_MM)


        uidp_w = float(NODES_TABLE_COL_UIDP_MM)
        if transform:
            col_w = (float(NODES_TABLE_W_MM) - uidp_w) / 4.0
            widths = [uidp_w, col_w, col_w, col_w, col_w]
        else:
            col_w = (float(NODES_TABLE_W_MM) - uidp_w) / 2.0
            widths = [uidp_w, col_w, col_w]

        tr_body = f"height:{body_row_h}mm;"
        tr_head = f"height:{header_row_h}mm;"
        th_style = f"font-weight:normal; padding:0 2px; {tr_head}"

        if transform:
            header = f"""
            <th style="{th_style}">{SP * 5}№</th>
            <th style="{th_style}">{SP * 5}X (СК-63)</th>
            <th style="{th_style}">{SP * 5}Y (СК-63)</th>
            <th style="{th_style}">{SP * 2}X (УСК-2000)</th>
            <th style="{th_style}">{SP * 2}Y (УСК-2000)</th>
            """
        else:
            header = f"""
            <th style="{th_style}">№</th>
            <th style="{th_style}">X</th>
            <th style="{th_style}">Y</th>
            """














        body = []
        td_base = f"padding:0 2px; {tr_body}"
        td_right = f"text-align:right; {td_base}"
        for i, r in enumerate(rows):
            bg = f"background:{NODES_TABLE_ROW_ALT_BG};" if i % 2 == 1 else ""
            if transform:
                body.append(
                    f"<tr style='{bg} {tr_body}'>"
                    f"<td style='{td_right}'>{r['uidp']}</td>"
                    f"<td style='{td_right}'>{r['x']:.2f}</td>"
                    f"<td style='{td_right}'>{r['y']:.2f}</td>"
                    f"<td style='{td_right}'>{r['x2']:.2f}</td>"
                    f"<td style='{td_right}'>{r['y2']:.2f}</td>"
                    "</tr>"
                )
            else:
                body.append(
                    f"<tr style='{bg} {tr_body}'>"
                    f"<td style='{td_right}'>{r['uidp']}</td>"
                    f"<td style='{td_right}'>{r['x']:.2f}</td>"
                    f"<td style='{td_right}'>{r['y']:.2f}</td>"
                    "</tr>"
                )


































        colgroup = "\n".join([f"<col style='width:{w:.2f}mm;'>" for w in widths])
        html = f"""
        <div style="width:{float(NODES_TABLE_W_MM):.2f}mm; text-align:center; font-size:{font_pt}pt; font-weight:normal;">
          <table style="
            width:{float(NODES_TABLE_W_MM):.2f}mm;
            border-collapse:collapse;
            border:0.1mm solid #888;
          ">
            <colgroup>
              {colgroup}
            </colgroup>
            <thead>
              <tr style="background:#f2f2f2; {tr_head}">
                {header}
              </tr>
            </thead>
            <tbody>
              {''.join(body)}
            </tbody>
          </table>
        </div>
        """




        return html, len(body)


    def _build_boundary_description_rows(self) -> Tuple[list[str], int]:
        """
        Повертає рядки для таблиці "Опис меж" (без заголовка).
        """
        txt = self._build_boundary_description()
        if not txt:
            return [], 0

        lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
        if not lines:
            return [], 0


        if lines[0].lower().startswith("опис меж"):
            lines = lines[1:]
        return lines, len(lines)

    def _text_width_mm(self, font: QFont, text: str) -> float:
        """
        Best-effort text width in millimeters for the given font.
        """
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

    def _build_boundary_description_items(self) -> list[tuple[str, str, str, str]]:
        """
        Returns items for the boundary description table:
        (from_letter, to_letter, proprietor_name, cadastral_number).
        """
        txt = self._build_boundary_description()
        if not txt:
            return []

        lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
        if not lines:
            return []
        if lines[0].lower().startswith("опис меж"):
            lines = lines[1:]

        items: list[tuple[str, str, str, str]] = []
        for ln in lines:

            try:
                left, rest = ln.split("–", 1)
            except ValueError:
                left, rest = ln, ""
            left = left.strip()
            rest = rest.strip()

            from_letter = ""
            to_letter = ""
            try:

                parts = left.replace("Від", "").replace("до", "").split()
                if len(parts) >= 2:
                    from_letter, to_letter = parts[0], parts[1]
            except Exception:
                from_letter, to_letter = "", ""


            name = rest
            kn = ""
            try:
                toks = [t for t in rest.split() if t]
                if toks and ":" in toks[-1]:
                    kn = toks[-1].strip()
                    name = " ".join(toks[:-1]).strip()
            except Exception:
                name, kn = rest, ""

            items.append((from_letter, to_letter, name, kn))

        return items

    def _build_boundary_description_table_html(self, font: QFont) -> Tuple[str, int, float]:
        """
        Формує HTML-таблицю (рядки) "Опис меж" у стилі таблиці координат.
        Повертає (html, rows_count, table_width_mm).
        """
        items = self._build_boundary_description_items()
        if not items:
            return "", 0, 0.0


        def esc(s: str) -> str:
            return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        body_row_h = float(NODES_TABLE_ROW_H_MM)
        tr_body = f"height:{body_row_h}mm;"



        seg_header = "Частина межі"
        owner_header = "Назва"
        kn_header = "Кадастровий номер"

        seg_texts = [seg_header] + [f"Від {a} до {b}".strip() for a, b, _, _ in items]
        owner_texts = [owner_header] + [nm or "" for _, _, nm, _ in items]
        kn_texts = [kn_header] + [kn or "" for _, _, _, kn in items]

        pad_mm = 4.0  # 2mm left + 2mm right
        w_seg = max(self._text_width_mm(font, t) for t in seg_texts) + pad_mm
        w_owner = max(self._text_width_mm(font, t) for t in owner_texts) + pad_mm
        w_kn = max(self._text_width_mm(font, t) for t in kn_texts) + pad_mm


        w_seg = max(w_seg, 22.0)
        w_owner = max(w_owner, 40.0)
        w_kn = max(w_kn, 35.0)

        table_w_mm = float(w_seg + w_owner + w_kn)

        rows_html = []
        td_left = f"text-align:left; padding:0 2px; {tr_body} white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"


        tr_head = f"height:{float(NODES_TABLE_HEADER_ROW_H_MM):.2f}mm;"
        th_style = f"font-weight:normal; padding:0 2px; {tr_head} text-align:center;"
        rows_html.append(
            f"<tr style='background:{NODES_TABLE_HEADER_BG}; {tr_head}'>"
            f"<th style='{th_style}'>{esc(seg_header)}</th>"
            f"<th style='{th_style}'>{esc(owner_header)}</th>"
            f"<th style='{th_style}'>{esc(kn_header)}</th>"
            "</tr>"
        )

        for i, (a, b, nm, kn) in enumerate(items):
            bg = f"background:{NODES_TABLE_ROW_ALT_BG};" if i % 2 == 1 else ""
            seg = f"Від {a} до {b}".strip()
            rows_html.append(
                f"<tr style='{bg} {tr_body}'>"
                f"<td style='{td_left}'>{esc(seg)}</td>"
                f"<td style='{td_left}'>{esc(nm)}</td>"
                f"<td style='{td_left}'>{esc(kn)}</td>"
                "</tr>"
            )

        colgroup = "\n".join(
            [
                f"<col style='width:{float(w_seg):.2f}mm;'>",
                f"<col style='width:{float(w_owner):.2f}mm;'>",
                f"<col style='width:{float(w_kn):.2f}mm;'>",
            ]
        )

        html = f"""
        <div style="width:{float(table_w_mm):.2f}mm; font-size:{float(font.pointSizeF() or NODES_TABLE_FONT_PT):.2f}pt; font-weight:normal;">
          <table style="
            width:{float(table_w_mm):.2f}mm;
            table-layout:fixed;
            border-collapse:collapse;
            border:{NODES_TABLE_BORDER_MM}mm solid #888;
          ">
            <colgroup>
              {colgroup}
            </colgroup>
            {''.join(rows_html)}
          </table>
        </div>
        """
        return html, len(items), table_w_mm

    def _add_boundary_description_table(self, layout):
        """
        Додає у layout HTML-таблицю "Опис меж".
        """
        f = QFont()
        f.setPointSizeF(float(NODES_TABLE_FONT_PT))
        desc_html, nrows, table_w_mm = self._build_boundary_description_table_html(font=f)
        if not desc_html:
            return

        desc = QgsLayoutItemLabel(layout)
        desc.setMode(QgsLayoutItemLabel.ModeHtml)
        desc.setText(desc_html)

        desc.setObjectName("Опис меж")
        desc.setId("Опис меж")

        layout.addLayoutItem(desc)


        desc_height = float(nrows) * float(NODES_TABLE_ROW_H_MM)

        desc.attemptResize(QgsLayoutSize(float(table_w_mm), desc_height, QgsUnitTypes.LayoutMillimeters))

        desc.attemptMove(
            QgsLayoutPoint(
                BOUNDARY_DESC_X_MM,
                BOUNDARY_DESC_Y_MM,
                QgsUnitTypes.LayoutMillimeters
            )
        )

    def _add_nodes_coordinates_table(self, layout):
        """
        Додає у layout HTML-таблицю координат вузлів.
        """
        nodes_html, nrows = self._build_nodes_table_html()
        if not nodes_html:
            return

        tbl = QgsLayoutItemLabel(layout)
        tbl.setMode(QgsLayoutItemLabel.ModeHtml)
        tbl.setText(nodes_html)

        tbl.setObjectName("Таблиця координат")
        tbl.setId("Таблиця координат")

        layout.addLayoutItem(tbl)


        total_h = NODES_TABLE_HEADER_ROW_H_MM + (int(nrows) * NODES_TABLE_ROW_H_MM)

        tbl.attemptResize(
            QgsLayoutSize(
                NODES_TABLE_W_MM,
                total_h,
                QgsUnitTypes.LayoutMillimeters
            )
        )

        tbl.attemptMove(
            QgsLayoutPoint(
                NODES_TABLE_X_MM,
                NODES_TABLE_Y_MM,
                QgsUnitTypes.LayoutMillimeters
            )
        )
        try:
            w = float(tbl.rect().width())
            h = float(tbl.rect().height())
            log_calls(logFile, f"Nodes table size (p1): {w:.2f}x{h:.2f} mm, rows={int(nrows)}")
        except Exception:
            pass

    def _add_nodes_coordinates_table_page2(
        self,
        layout,
        x_mm: float,
        w_mm: float,
        title_y_mm: float,
        font: QFont,
        xml_root=None,
        restrictions_layer=None,
        leases_layer=None,
        subleases_layer=None,
    ):
        """
        Додає таблицю координат на 2-й аркуш: заголовок + таблиця, обидва по центру відносно полів.

        Вимоги:
        - 5 мм відступ після заголовка аркуша;
        - шрифт як у ParcelTextBlock;
        - +100% висота рядка;
        - висота об'єкта "Таблиця координат:p2" = висоті таблиці.
        """
        try:
            font_pt = float(font.pointSizeF()) if font and font.pointSizeF() > 0 else float(NODES_TABLE_FONT_PT)
        except Exception:
            font_pt = float(NODES_TABLE_FONT_PT)

        nodes_html, nrows = self._build_nodes_table_html(font_pt=font_pt)
        if not nodes_html:
            return

        y_off = self._page_y_offset(layout, 2)
        top_y = float(title_y_mm) + float(TITLE_H_MM) + 5.0 + float(y_off)


        head = QgsLayoutItemLabel(layout)
        head.setText("Таблиця координат точок повороту межі земельної ділянки")
        try:
            head.setFont(QFont(font))
        except Exception:
            pass
        layout.addLayoutItem(head)
        head_h = float(NODES_TABLE_TITLE_H_MM)
        head_x = float(x_mm)
        try:
            head.adjustSizeToText()
            hw = float(head.rect().width())
            head_x = float(x_mm) + max(0.0, (float(w_mm) - hw) / 2.0)
            head.attemptResize(QgsLayoutSize(hw, head_h, QgsUnitTypes.LayoutMillimeters))
        except Exception:
            head.attemptResize(QgsLayoutSize(float(w_mm), head_h, QgsUnitTypes.LayoutMillimeters))
            head.setHAlign(Qt.AlignHCenter)
            head.setVAlign(Qt.AlignVCenter)
        head.attemptMove(QgsLayoutPoint(head_x, top_y, QgsUnitTypes.LayoutMillimeters))
        head.setObjectName("Заголовок таблиці координат:p2")
        head.setId("Заголовок таблиці координат:p2")


        tbl = QgsLayoutItemLabel(layout)
        tbl.setMode(QgsLayoutItemLabel.ModeHtml)
        tbl.setText(nodes_html)
        try:
            tbl.setFont(QFont(font))
        except Exception:
            pass
        tbl.setObjectName("Таблиця координат:p2")
        tbl.setId("Таблиця координат:p2")
        layout.addLayoutItem(tbl)

        expected_w = float(NODES_TABLE_W_MM)
        expected_h = float(NODES_TABLE_HEADER_ROW_H_MM) + (int(nrows) * float(NODES_TABLE_ROW_H_MM))

        tbl_x = float(x_mm)
        tbl_y = top_y + head_h
        tbl.attemptResize(QgsLayoutSize(expected_w, expected_h, QgsUnitTypes.LayoutMillimeters))
        tbl_x = float(x_mm) + max(0.0, (float(w_mm) - expected_w) / 2.0)
        try:
            tw = float(tbl.rect().width())
            th = float(tbl.rect().height())
            log_calls(
                logFile,
                f"Nodes table size (p2): expected {expected_w:.2f}x{expected_h:.2f} mm, item {tw:.2f}x{th:.2f} mm, rows={int(nrows)}",
            )
        except Exception:
            pass
        tbl.attemptMove(QgsLayoutPoint(tbl_x, tbl_y, QgsUnitTypes.LayoutMillimeters))




        try:
            boundary_html, brow_count, boundary_w_mm = self._build_boundary_description_table_html(
                font=QFont(font),
            )
            if boundary_html:
                gap = 5.0
                next_y = float(tbl_y) + float(expected_h) + gap

                bhead = QgsLayoutItemLabel(layout)
                bhead.setText("Опис меж з суміжниками")
                try:
                    bhead.setFont(QFont(font))
                except Exception:
                    pass
                layout.addLayoutItem(bhead)
                bhead_h = float(NODES_TABLE_TITLE_H_MM)
                bhead.attemptResize(QgsLayoutSize(float(w_mm), bhead_h, QgsUnitTypes.LayoutMillimeters))
                bhead.setHAlign(Qt.AlignHCenter)
                bhead.setVAlign(Qt.AlignVCenter)
                bhead.attemptMove(QgsLayoutPoint(float(x_mm), next_y, QgsUnitTypes.LayoutMillimeters))
                bhead.setObjectName("Опис меж заголовок:p2")
                bhead.setId("Опис меж заголовок:p2")

                btbl = QgsLayoutItemLabel(layout)
                btbl.setMode(QgsLayoutItemLabel.ModeHtml)
                btbl.setText(boundary_html)
                try:
                    btbl.setFont(QFont(font))
                except Exception:
                    pass
                btbl.setObjectName("Опис меж:p2")
                btbl.setId("Опис меж:p2")
                layout.addLayoutItem(btbl)



                b_h = float(NODES_TABLE_HEADER_ROW_H_MM) + float(brow_count) * float(NODES_TABLE_ROW_H_MM) + 2.0
                btbl.attemptResize(QgsLayoutSize(float(boundary_w_mm), b_h, QgsUnitTypes.LayoutMillimeters))
                bx = float(x_mm) + max(0.0, (float(w_mm) - float(boundary_w_mm)) / 2.0)
                btbl.attemptMove(QgsLayoutPoint(bx, next_y + bhead_h, QgsUnitTypes.LayoutMillimeters))




                try:
                    exp_gap = 5.0
                    exp_y = float(next_y + bhead_h) + float(b_h) + exp_gap

                    etitle = QgsLayoutItemLabel(layout)
                    etitle.setText("Експлікація угідь")
                    try:
                        etitle.setFont(QFont(font))
                    except Exception:
                        pass
                    layout.addLayoutItem(etitle)
                    etitle_h = float(NODES_TABLE_TITLE_H_MM)
                    etitle.attemptResize(QgsLayoutSize(float(w_mm), etitle_h, QgsUnitTypes.LayoutMillimeters))
                    etitle.setHAlign(Qt.AlignHCenter)
                    etitle.setVAlign(Qt.AlignVCenter)
                    etitle.attemptMove(QgsLayoutPoint(float(x_mm), exp_y, QgsUnitTypes.LayoutMillimeters))
                    etitle.setObjectName("Експлікація угідь заголовок:p2")
                    etitle.setId("Експлікація угідь заголовок:p2")

                    ehtml, erows, e_w = LandsExplicationTable.build_html(
                        xml_root=xml_root,
                        font=QFont(font),
                        body_row_h_mm=float(NODES_TABLE_ROW_H_MM),
                        header_row_h_mm=float(NODES_TABLE_HEADER_ROW_H_MM),
                    )
                    if ehtml and erows:
                        etbl = QgsLayoutItemLabel(layout)
                        etbl.setMode(QgsLayoutItemLabel.ModeHtml)
                        etbl.setText(ehtml)
                        try:
                            etbl.setFont(QFont(font))
                        except Exception:
                            pass
                        etbl.setObjectName("Експлікація угідь:p2")
                        etbl.setId("Експлікація угідь:p2")
                        layout.addLayoutItem(etbl)

                        e_h = float(NODES_TABLE_HEADER_ROW_H_MM) + float(erows) * float(NODES_TABLE_ROW_H_MM) + 2.0
                        etbl.attemptResize(QgsLayoutSize(float(e_w), e_h, QgsUnitTypes.LayoutMillimeters))
                        ex = float(x_mm) + max(0.0, (float(w_mm) - float(e_w)) / 2.0)
                        etbl.attemptMove(QgsLayoutPoint(ex, exp_y + etitle_h, QgsUnitTypes.LayoutMillimeters))




                        try:
                            def _has_features(layer) -> bool:
                                if layer is None:
                                    return False
                                try:
                                    for _ in layer.getFeatures():
                                        return True
                                except Exception:
                                    return False
                                return False

                            y_cursor = float(exp_y + etitle_h) + float(e_h) + 5.0

                            rtitle = QgsLayoutItemLabel(layout)
                            rtitle.setText("Перелік частин ділянки з обмеженнями")
                            try:
                                rtitle.setFont(QFont(font))
                            except Exception:
                                pass
                            layout.addLayoutItem(rtitle)
                            rtitle_h = float(NODES_TABLE_TITLE_H_MM)
                            rtitle.attemptResize(QgsLayoutSize(float(w_mm), rtitle_h, QgsUnitTypes.LayoutMillimeters))
                            rtitle.setHAlign(Qt.AlignHCenter)
                            rtitle.setVAlign(Qt.AlignVCenter)
                            rtitle.attemptMove(QgsLayoutPoint(float(x_mm), y_cursor, QgsUnitTypes.LayoutMillimeters))
                            rtitle.setObjectName("Обмеження заголовок:p2")
                            rtitle.setId("Обмеження заголовок:p2")

                            rhtml, rrows, r_w = RestrictionsPartsTable.build_html(
                                xml_root=xml_root,
                                restrictions_layer=restrictions_layer,
                                font=QFont(font),
                                body_row_h_mm=float(NODES_TABLE_ROW_H_MM),
                                header_row_h_mm=float(NODES_TABLE_HEADER_ROW_H_MM),
                            )
                            if rhtml and rrows:
                                rtbl = QgsLayoutItemLabel(layout)
                                rtbl.setMode(QgsLayoutItemLabel.ModeHtml)
                                rtbl.setText(rhtml)
                                try:
                                    rtbl.setFont(QFont(font))
                                except Exception:
                                    pass
                                rtbl.setObjectName("Обмеження:p2")
                                rtbl.setId("Обмеження:p2")
                                layout.addLayoutItem(rtbl)

                                r_h = float(NODES_TABLE_HEADER_ROW_H_MM) + float(rrows) * float(NODES_TABLE_ROW_H_MM) + 2.0
                                rtbl.attemptResize(QgsLayoutSize(float(r_w), r_h, QgsUnitTypes.LayoutMillimeters))
                                rx = float(x_mm) + max(0.0, (float(w_mm) - float(r_w)) / 2.0)
                                rtbl.attemptMove(QgsLayoutPoint(rx, y_cursor + rtitle_h, QgsUnitTypes.LayoutMillimeters))
                                y_cursor = float(y_cursor + rtitle_h + r_h)

                            if _has_features(leases_layer):
                                y_cursor += 5.0
                                ltitle = QgsLayoutItemLabel(layout)
                                ltitle.setText("Перелік частин ділянки переданих в оренду")
                                try:
                                    ltitle.setFont(QFont(font))
                                except Exception:
                                    pass
                                layout.addLayoutItem(ltitle)
                                ltitle_h = float(NODES_TABLE_TITLE_H_MM)
                                ltitle.attemptResize(QgsLayoutSize(float(w_mm), ltitle_h, QgsUnitTypes.LayoutMillimeters))
                                ltitle.setHAlign(Qt.AlignHCenter)
                                ltitle.setVAlign(Qt.AlignVCenter)
                                ltitle.attemptMove(QgsLayoutPoint(float(x_mm), y_cursor, QgsUnitTypes.LayoutMillimeters))
                                ltitle.setObjectName("Оренда заголовок:p2")
                                ltitle.setId("Оренда заголовок:p2")

                                lhtml, lrows, l_w = LeasesPartsTable.build_html(
                                    xml_root=xml_root,
                                    font=QFont(font),
                                    body_row_h_mm=float(NODES_TABLE_ROW_H_MM),
                                    header_row_h_mm=float(NODES_TABLE_HEADER_ROW_H_MM),
                                )
                                if lhtml and lrows:
                                    ltbl = QgsLayoutItemLabel(layout)
                                    ltbl.setMode(QgsLayoutItemLabel.ModeHtml)
                                    ltbl.setText(lhtml)
                                    try:
                                        ltbl.setFont(QFont(font))
                                    except Exception:
                                        pass
                                    ltbl.setObjectName("Оренда:p2")
                                    ltbl.setId("Оренда:p2")
                                    layout.addLayoutItem(ltbl)

                                    l_h = float(NODES_TABLE_HEADER_ROW_H_MM) + float(lrows) * float(NODES_TABLE_ROW_H_MM) + 2.0
                                    ltbl.attemptResize(QgsLayoutSize(float(l_w), l_h, QgsUnitTypes.LayoutMillimeters))
                                    lx = float(x_mm) + max(0.0, (float(w_mm) - float(l_w)) / 2.0)
                                    ltbl.attemptMove(QgsLayoutPoint(lx, y_cursor + ltitle_h, QgsUnitTypes.LayoutMillimeters))
                                    y_cursor = float(y_cursor + ltitle_h + l_h)

                            if _has_features(subleases_layer):
                                y_cursor += 5.0
                                stitle = QgsLayoutItemLabel(layout)
                                stitle.setText("Перелік частин ділянки переданих у суборенду")
                                try:
                                    stitle.setFont(QFont(font))
                                except Exception:
                                    pass
                                layout.addLayoutItem(stitle)
                                stitle_h = float(NODES_TABLE_TITLE_H_MM)
                                stitle.attemptResize(QgsLayoutSize(float(w_mm), stitle_h, QgsUnitTypes.LayoutMillimeters))
                                stitle.setHAlign(Qt.AlignHCenter)
                                stitle.setVAlign(Qt.AlignVCenter)
                                stitle.attemptMove(QgsLayoutPoint(float(x_mm), y_cursor, QgsUnitTypes.LayoutMillimeters))
                                stitle.setObjectName("Суборенда заголовок:p2")
                                stitle.setId("Суборенда заголовок:p2")

                                shtml, srows, s_w = SubleasesPartsTable.build_html(
                                    xml_root=xml_root,
                                    font=QFont(font),
                                    body_row_h_mm=float(NODES_TABLE_ROW_H_MM),
                                    header_row_h_mm=float(NODES_TABLE_HEADER_ROW_H_MM),
                                )
                                if shtml and srows:
                                    stbl = QgsLayoutItemLabel(layout)
                                    stbl.setMode(QgsLayoutItemLabel.ModeHtml)
                                    stbl.setText(shtml)
                                    try:
                                        stbl.setFont(QFont(font))
                                    except Exception:
                                        pass
                                    stbl.setObjectName("Суборенда:p2")
                                    stbl.setId("Суборенда:p2")
                                    layout.addLayoutItem(stbl)

                                    s_h = float(NODES_TABLE_HEADER_ROW_H_MM) + float(srows) * float(NODES_TABLE_ROW_H_MM) + 2.0
                                    stbl.attemptResize(QgsLayoutSize(float(s_w), s_h, QgsUnitTypes.LayoutMillimeters))
                                    sx = float(x_mm) + max(0.0, (float(w_mm) - float(s_w)) / 2.0)
                                    stbl.attemptMove(QgsLayoutPoint(sx, y_cursor + stitle_h, QgsUnitTypes.LayoutMillimeters))
                                    y_cursor = float(y_cursor + stitle_h + s_h)
                        except Exception as e:
                            log_calls(logFile, f"Page2 restrictions parts add failed: {e}")
                except Exception as e:
                    log_calls(logFile, f"Page2 lands explication add failed: {e}")
        except Exception as e:
            log_calls(logFile, f"Page2 boundary table add failed: {e}")






    def create_layout(self, scale_value: int, show_ruler: bool = False):
        if LOG:
            log_calls(logFile, f"create_layout scale=1:{scale_value}")

        mgr = self.project.layoutManager()
        name = f"Кадастровий план {self.parent_group.name()}"

        old = mgr.layoutByName(name)
        if old:
            mgr.removeLayout(old)

        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()
        layout.setName(name)

        if not mgr.addLayout(layout):
            raise RuntimeError("Layout create failed")


        page = layout.pageCollection().page(0)
        page.setPageSize(QgsLayoutSize(PAGE_W_MM, PAGE_H_MM, QgsUnitTypes.LayoutMillimeters))


        try:
            from qgis.core import QgsLayoutItemPage

            pc = layout.pageCollection()
            if int(pc.pageCount()) < 2:
                p2 = QgsLayoutItemPage(layout)
                p2.setPageSize(QgsLayoutSize(PAGE_W_MM, PAGE_H_MM, QgsUnitTypes.LayoutMillimeters))
                pc.addPage(p2)
        except Exception:
            pass






















        content_x = MARGIN_LEFT_MM
        content_w = PAGE_W_MM - MARGIN_LEFT_MM - MARGIN_RIGHT_MM
        title_y = MARGIN_TOP_MM
        map_y = MARGIN_TOP_MM + TITLE_H_MM

        xml_root = None
        try:
            if self.plugin and getattr(self.plugin, "dockwidget", None):
                xml_data = self.plugin.dockwidget.get_xml_data_for_group(self.parent_group.name())
                if xml_data and getattr(xml_data, "tree", None):
                    xml_root = xml_data.tree.getroot()
        except Exception:
            xml_root = None

        cadastral_number = self._build_cadastral_number(xml_root)
        executor_sig_name = self._build_executor_signature_name(xml_root)
        executor_company = self._build_executor_company(xml_root)
        customer_name = self._build_customer_name(xml_root)
        land_categories = self._ini_section_map("LandCategories")
        land_purposes = self._ini_section_map("LandPurposeSubchapters")
        category_code = self._xml_first_text(xml_root, "//*[local-name()='CategoryPurposeInfo']/*[local-name()='Category'][1]")
        purpose_code = self._xml_first_text(xml_root, "//*[local-name()='CategoryPurposeInfo']/*[local-name()='Purpose'][1]")
        category_text = land_categories.get(category_code, "") if category_code else ""
        purpose_text = land_purposes.get(purpose_code, "") if purpose_code else ""

        area_ha_txt = ""
        try:
            area_raw = self._xml_first_text(xml_root, "//*[local-name()='ParcelMetricInfo']/*[local-name()='Area']/*[local-name()='Size'][1]")
            area_unit = self._xml_first_text(
                xml_root,
                "//*[local-name()='ParcelMetricInfo']/*[local-name()='Area']/*[local-name()='MeasurementUnit'][1]",
            )
            if area_raw:
                area_val = float(str(area_raw).replace(",", "."))

                if str(area_unit).strip() in ("М", "м", "M", "m"):
                    area_val = area_val / 10000.0
                area_ha_txt = f"{area_val:.4f}"
        except Exception:
            area_ha_txt = ""

        parcel_location = self._build_parcel_location_formatted(xml_root)

        page_count = 1
        try:
            page_count = int(layout.pageCollection().pageCount())
        except Exception:
            page_count = 1


        map_item = QgsLayoutItemMap(layout)
        map_item.setId("Ділянка")
        map_item.setObjectName("Ділянка")
        layout.addLayoutItem(map_item)

        map_item.attemptMove(QgsLayoutPoint(content_x, map_y, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(MAP_SIDE_MM, MAP_SIDE_MM, QgsUnitTypes.LayoutMillimeters))


        neighbors = self._find_layer_exact(self.cadastral_plan_group, "Суміжники")
        extent = neighbors.extent() if neighbors else self._group_extent()

        if not extent:
            QMessageBox.critical(self.iface.mainWindow(), "Помилка", "Немає екстента для карти")
            return None


        cx = (extent.xMinimum() + extent.xMaximum()) / 2.0
        cy = (extent.yMinimum() + extent.yMaximum()) / 2.0
        side = max(extent.width(), extent.height()) * float(PARCEL_MARGIN_FACTOR)
        half = side / 2.0
        square_extent = QgsRectangle(cx - half, cy - half, cx + half, cy + half)

        map_item.setExtent(square_extent)
        map_item.setScale(int(scale_value))
        map_item.refresh()

        if show_ruler:
            try:
                from .ruler import Ruler

                Ruler(layout).add(
                    map_x_mm=content_x,
                    map_y_mm=map_y,
                    map_side_mm=MAP_SIDE_MM,
                    scale_value=int(scale_value),
                )
            except Exception as e:
                log_calls(logFile, f"Ruler add failed: {e}")




        title_bg = QgsLayoutItemShape(layout)
        title_bg.setShapeType(QgsLayoutItemShape.Rectangle)
        title_bg.attemptMove(QgsLayoutPoint(content_x, title_y, QgsUnitTypes.LayoutMillimeters))
        title_bg.attemptResize(QgsLayoutSize(content_w, TITLE_H_MM, QgsUnitTypes.LayoutMillimeters))
        title_bg_symbol = QgsFillSymbol.createSimple({
            "color": "242,242,242,255",          # як у шапці таблиць (#f2f2f2)
            "outline_color": "136,136,136,255",  # як у таблицях
            "outline_width": "0.1",
            "outline_style": "solid"
        })
        title_bg.setSymbol(title_bg_symbol)
        layout.addLayoutItem(title_bg)




        title = QgsLayoutItemLabel(layout)
        sheet_title = f"Кадастровий план земельної ділянки {cadastral_number}".strip()
        title.setText(f"{sheet_title} (аркуш 1 з {page_count})")

        fnt = QFont()
        fnt.setPointSizeF(10)
        fnt.setBold(False)
        title.setFont(fnt)


        layout.addLayoutItem(title)  # IMPORTANT before attemptResize

        title.attemptResize(QgsLayoutSize(content_w, TITLE_H_MM, QgsUnitTypes.LayoutMillimeters))
        title.setHAlign(Qt.AlignHCenter)
        title.setVAlign(Qt.AlignVCenter)
        title.attemptMove(
            QgsLayoutPoint(
                content_x,
                title_y,
                QgsUnitTypes.LayoutMillimeters,
            )
        )




        sig = QgsLayoutItemLabel(layout)
        sig.setObjectName("Signature")
        sig.setId("Signature")
        sig_text = (
            "Сертифікований інженер-землевпорядник "
            "_____________________________ "
            f"{executor_sig_name}"
        ).rstrip()
        sig.setText(sig_text)
        sig.setFont(fnt)
        layout.addLayoutItem(sig)
        try:
            sig.setWordWrap(False)
        except Exception:
            pass
        sig_h = TITLE_H_MM
        sig_y = PAGE_H_MM - MARGIN_BOTTOM_MM - sig_h
        sig.attemptResize(QgsLayoutSize(content_w, sig_h, QgsUnitTypes.LayoutMillimeters))
        sig.setHAlign(Qt.AlignLeft)
        sig.setVAlign(Qt.AlignVCenter)
        sig.attemptMove(QgsLayoutPoint(content_x, sig_y, QgsUnitTypes.LayoutMillimeters))




        scale_label = QgsLayoutItemLabel(layout)
        scale_label.setText(f"Масштаб 1:{int(scale_value)}")

        fnt2 = QFont()
        fnt2.setPointSizeF(9)
        fnt2.setBold(False)
        scale_label.setFont(fnt2)


        layout.addLayoutItem(scale_label)

        scale_label.attemptResize(QgsLayoutSize(MAP_SIDE_MM, SCALE_H_MM, QgsUnitTypes.LayoutMillimeters))
        scale_label.setHAlign(Qt.AlignHCenter)
        scale_label.setVAlign(Qt.AlignVCenter)

        scale_label.attemptMove(
            QgsLayoutPoint(
                content_x,
                map_y + MAP_SIDE_MM + OVERLAY_PAD_MM,
                QgsUnitTypes.LayoutMillimeters,
            )
        )




        try:
            Symbols(
                layout,
                parent_group=self.parent_group,
                cadastral_plan_group=self.cadastral_plan_group,
                xml_root=xml_root,
            ).add(
                x_mm=content_x,
                y_mm=map_y + MAP_SIDE_MM + OVERLAY_PAD_MM + SCALE_H_MM + 1.0,
                table_w_mm=MAP_SIDE_MM,
                row_h_mm=10.0,
            )
        except Exception as e:
            log_calls(logFile, f"Symbols add failed: {e}")




        try:
            symbols_y = map_y + MAP_SIDE_MM + OVERLAY_PAD_MM + SCALE_H_MM + 1.0
            symbols_row_h = 10.0
            restrictions_count = 0
            restrictions_layer = None
            try:
                if self.cadastral_plan_group:
                    restrictions_layer = self._find_layer_exact(self.cadastral_plan_group, "Обмеження")
            except Exception:
                restrictions_layer = None
            if restrictions_layer is not None:
                seen_ids = set()
                for ftr in restrictions_layer.getFeatures():
                    try:
                        geom = ftr.geometry()
                        if geom is None or geom.isEmpty():
                            continue
                    except Exception:
                        continue
                    oid = None
                    try:
                        oid = ftr["object_id"]
                    except Exception:
                        oid = None
                    if oid is None:
                        continue
                    try:
                        oid_int = int(str(oid).strip())
                    except Exception:
                        continue
                    if oid_int in seen_ids:
                        continue
                    seen_ids.add(oid_int)
                restrictions_count = len(seen_ids)

            extra_rows = int(math.ceil(float(restrictions_count) / 3.0)) if restrictions_count else 0
            symbols_h = float(Symbols.TITLE_H_MM) + float((2 + extra_rows) * symbols_row_h)
            symbols_bottom_y = symbols_y + symbols_h
            available_h = sig_y - symbols_bottom_y

            if available_h > 4.0:
                paragraph = QgsLayoutItemLabel(layout)
                paragraph.setObjectName("ParcelTextBlock")
                paragraph.setId("ParcelTextBlock")

                exec_name = executor_company or executor_sig_name
                line1 = (
                    f"Земельна ділянка із земель: {category_text} "
                    f"за цільовим призначенням {purpose_text} (код {purpose_code}) "
                    f"площею {area_ha_txt} га, розташована: {parcel_location}."
                )
                line2 = (
                    "Кадастровий план є частиною документації із землеустрою, "
                    f"виготовленої {exec_name} на замовлення {customer_name}."
                )
                paragraph.setText(f"{line1}\n{line2}".strip())


                font_size = 10.0
                if available_h < 12.0:
                    font_size = 9.0
                if available_h < 9.0:
                    font_size = 8.0

                pfont = QFont(fnt)
                pfont.setPointSizeF(font_size)
                pfont.setBold(False)
                paragraph.setFont(pfont)
                try:
                    paragraph.setWordWrap(True)
                except Exception:
                    pass
                layout.addLayoutItem(paragraph)
                paragraph.attemptResize(QgsLayoutSize(content_w, available_h, QgsUnitTypes.LayoutMillimeters))
                paragraph.setHAlign(Qt.AlignLeft)

                paragraph.setVAlign(Qt.AlignVCenter)
                paragraph.attemptMove(QgsLayoutPoint(content_x, symbols_bottom_y, QgsUnitTypes.LayoutMillimeters))
        except Exception as e:
            log_calls(logFile, f"Parcel text block add failed: {e}")




















































        self.add_neighbor_letters(layout, map_item)




        try:
            page_count = int(layout.pageCollection().pageCount())
        except Exception:
            page_count = 1




        try:
            parcel_text_font = None
            it = layout.items()
            for item in it:
                try:
                    if item and getattr(item, "id", lambda: "")() == "ParcelTextBlock":
                        parcel_text_font = item.font()
                        break
                except Exception:
                    continue
            if page_count >= 2:
                restrictions_layer = None
                try:
                    if self.cadastral_plan_group:
                        restrictions_layer = self._find_layer_exact(self.cadastral_plan_group, "Обмеження")
                except Exception:
                    restrictions_layer = None
                leases_layer = None
                subleases_layer = None
                try:
                    if self.cadastral_plan_group:
                        leases_layer = self._find_layer_exact(self.cadastral_plan_group, "Оренда")
                except Exception:
                    leases_layer = None
                try:
                    if self.cadastral_plan_group:
                        subleases_layer = self._find_layer_exact(self.cadastral_plan_group, "Суборенда")
                except Exception:
                    subleases_layer = None
                self._add_nodes_coordinates_table_page2(
                    layout,
                    x_mm=content_x,
                    w_mm=content_w,
                    title_y_mm=title_y,
                    font=parcel_text_font or fnt,
                    xml_root=xml_root,
                    restrictions_layer=restrictions_layer,
                    leases_layer=leases_layer,
                    subleases_layer=subleases_layer,
                )
        except Exception as e:
            log_calls(logFile, f"Page2 nodes table add failed: {e}")

        try:
            title.setText(f"{sheet_title} (аркуш 1 з {page_count})")
        except Exception:
            pass

        for page_idx in range(2, page_count + 1):
            y_off = self._page_y_offset(layout, page_idx)


            bg = QgsLayoutItemShape(layout)
            bg.setShapeType(QgsLayoutItemShape.Rectangle)
            bg.attemptMove(QgsLayoutPoint(content_x, title_y + y_off, QgsUnitTypes.LayoutMillimeters))
            bg.attemptResize(QgsLayoutSize(content_w, TITLE_H_MM, QgsUnitTypes.LayoutMillimeters))
            try:
                bg.setSymbol(title_bg_symbol)
            except Exception:
                pass
            bg.setObjectName(f"TitleBg:p{page_idx}")
            bg.setId(f"TitleBg:p{page_idx}")
            layout.addLayoutItem(bg)


            t = QgsLayoutItemLabel(layout)
            t.setText(f"{sheet_title} (аркуш {page_idx} з {page_count})")
            t.setFont(fnt)
            layout.addLayoutItem(t)
            t.attemptResize(QgsLayoutSize(content_w, TITLE_H_MM, QgsUnitTypes.LayoutMillimeters))
            t.setHAlign(Qt.AlignHCenter)
            t.setVAlign(Qt.AlignVCenter)
            t.attemptMove(QgsLayoutPoint(content_x, title_y + y_off, QgsUnitTypes.LayoutMillimeters))
            t.setObjectName(f"Title:p{page_idx}")
            t.setId(f"Title:p{page_idx}")


            s = QgsLayoutItemLabel(layout)
            s.setText(sig_text)
            s.setFont(fnt)
            layout.addLayoutItem(s)
            try:
                s.setWordWrap(False)
            except Exception:
                pass
            s.attemptResize(QgsLayoutSize(content_w, sig_h, QgsUnitTypes.LayoutMillimeters))
            s.setHAlign(Qt.AlignLeft)
            s.setVAlign(Qt.AlignVCenter)
            s.attemptMove(QgsLayoutPoint(content_x, sig_y + y_off, QgsUnitTypes.LayoutMillimeters))
            s.setObjectName(f"Signature:p{page_idx}")
            s.setId(f"Signature:p{page_idx}")

        self.iface.openLayoutDesigner(layout)
        return layout




    def add_neighbor_letters(self, layout, map_item):
        """
        Розставляє літери суміжників біля стрілок «вусів».
        Літери горизонтальні (rotation=0).
        """
        cad = self.cadastral_plan_group
        if not cad:
            return

        nodes = self._find_layer_exact(cad, "Вузли суміжників")
        lines = self._find_layer_exact(cad, "Суміжники")
        parcel = self._find_layer_exact(cad, "Ділянка")
        nodes_root = self._find_layer_exact(self.parent_group, "Вузли")

        if not nodes or not lines or not parcel or not nodes_root:
            return

        F_NODE_UIDP = "PN"
        F_NODE_LIT = "LITERA"
        F_SHAPE = "object_shape"


        parcel_shape = str(next(parcel.getFeatures())[F_SHAPE])
        base = [s for s in parcel_shape.split("|")[0].split("-") if s]
        if base and base[0] == base[-1]:
            base = base[:-1]
        doubled = base + base

        uidp_to_pt = {str(f["uidp"]): f.geometry().asPoint() for f in nodes_root.getFeatures()}
        uidp_to_lit: Dict[str, str] = {str(f[F_NODE_UIDP]).strip(): str(f[F_NODE_LIT]).strip() for f in nodes.getFeatures()}

        def contains_sequence(inner):
            if not inner:
                return False
            for i in range(len(base)):
                if doubled[i:i + len(inner)] == inner:
                    return True
            return False

        font = QFont()
        font.setPointSizeF(NEIGHBOR_FONT_PT)
        seen_whiskers = set()
        used_letters = set()

        for f in lines.getFeatures():
            shape = [str(s).strip() for s in str(f[F_SHAPE]).split("-") if str(s).strip()]
            if len(shape) < 3:
                continue

            inner = shape[1:-1]
            rev_inner = list(reversed(inner))

            match_forward = contains_sequence(inner)
            match_reversed = contains_sequence(rev_inner)



            if match_forward and not match_reversed:
                place_uidp = shape[0]
                shared_uidp = shape[1]
            elif match_reversed and not match_forward:
                place_uidp = shape[-1]
                shared_uidp = shape[-2]
            else:



                boundary_uidps = set(base)
                candidates = []

                shared_left = next(
                    (u for u in shape[1:] if u in boundary_uidps and u in uidp_to_lit),
                    None
                )
                if shared_left:
                    candidates.append((shape[0], shared_left))

                shared_right = next(
                    (u for u in reversed(shape[:-1]) if u in boundary_uidps and u in uidp_to_lit),
                    None
                )
                if shared_right:
                    candidates.append((shape[-1], shared_right))

                if not candidates:
                    continue

                place_uidp, shared_uidp = candidates[0]
                for cand_place, cand_shared in candidates:
                    cand_letter = uidp_to_lit.get(cand_shared)
                    if cand_letter and cand_letter not in used_letters:
                        place_uidp, shared_uidp = cand_place, cand_shared
                        break

            letter = uidp_to_lit.get(shared_uidp)
            if not letter:
                continue
            used_letters.add(letter)



            whisker_key = (min(place_uidp, shared_uidp), max(place_uidp, shared_uidp))
            if whisker_key in seen_whiskers:
                continue
            seen_whiskers.add(whisker_key)

            place_pt = uidp_to_pt.get(place_uidp)
            shared_pt = uidp_to_pt.get(shared_uidp)
            if not place_pt or not shared_pt:
                continue

            place_l = self._map_xy_to_layout_mm(map_item, place_pt.x(), place_pt.y())
            shared_l = self._map_xy_to_layout_mm(map_item, shared_pt.x(), shared_pt.y())


            dx, dy = _unit(place_l[0] - shared_l[0], place_l[1] - shared_l[1])


            nx, ny = dy, -dx

            tmp = QgsLayoutItemLabel(layout)
            tmp.setText(letter)
            tmp.setFont(font)
            tmp.adjustSizeToText()
            h = tmp.rect().height()

            x = place_l[0] + nx * h
            y = place_l[1] + ny * h

            lbl = QgsLayoutItemLabel(layout)
            lbl.setText(letter)
            lbl.setFont(font)
            lbl.adjustSizeToText()
            layout.addLayoutItem(lbl)

            lbl.setReferencePoint(4)  # center
            lbl.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))


    def _build_boundary_description(self) -> str:
        """
        Формує текст блоку 'Опис меж' на основі XML.
        """

        plugin = self.plugin
        if not plugin or not plugin.dockwidget:
            return ""

        xml_data = None
        for xd in plugin.dockwidget.opened_xmls:
            if xd.group_name == self.parent_group.name():
                xml_data = xd
                break

        if not xml_data or not xml_data.tree:
            return ""

        root = xml_data.tree.getroot()


        try:
            adj_units = root.xpath(
                "//*[local-name()='AdjacentUnits']/*[local-name()='AdjacentUnitInfo']"
            )
        except Exception:
            adj_units = root.findall(".//AdjacentUnits/AdjacentUnitInfo")

        if not adj_units:
            return ""



        letters = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЮЯ"

        lines = ["Опис меж:"]

        count = min(len(adj_units), len(letters))
        for i in range(count):
            adj = adj_units[i]
            A = letters[i]
            B = letters[(i + 1) % count]


            name = ""


            try:
                legal = adj.xpath(".//*[local-name()='Proprietor']/*[local-name()='LegalEntity']/*[local-name()='Name'][1]")
            except Exception:
                legal = []
            if legal and getattr(legal[0], "text", None):
                name = str(legal[0].text).strip()
            else:
                def _first(xpath_expr: str) -> str:
                    try:
                        res = adj.xpath(xpath_expr)
                        if res and getattr(res[0], "text", None):
                            return str(res[0].text).strip()
                    except Exception:
                        return ""
                    return ""

                parts = [
                    _first(".//*[local-name()='Proprietor']/*[local-name()='NaturalPerson']/*[local-name()='FullName']/*[local-name()='LastName'][1]"),
                    _first(".//*[local-name()='Proprietor']/*[local-name()='NaturalPerson']/*[local-name()='FullName']/*[local-name()='FirstName'][1]"),
                    _first(".//*[local-name()='Proprietor']/*[local-name()='NaturalPerson']/*[local-name()='FullName']/*[local-name()='MiddleName'][1]"),
                ]
                name = " ".join(p for p in parts if p)


            try:
                kn_el = adj.xpath("./*[local-name()='CadastralNumber'][1]")
            except Exception:
                kn_el = []
            kn = ""
            if kn_el and getattr(kn_el[0], "text", None):
                kn = str(kn_el[0].text).strip()

            lines.append(f"Від {A} до {B} – {name} {kn}")

        return "\n".join(lines)
