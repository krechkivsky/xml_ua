"""
boundary_agreement_layout.py

Формування "Акт погодження меж" у QGIS Layout.
Стиль/поля/підпис — максимально сумісні з plan_layout.py (кадастровий план),
але без мітки масштабу та без таблиці умовних позначень.
"""

from __future__ import annotations

from typing import Tuple

from qgis.core import (
    QgsFillSymbol,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemShape,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
    Qgis,
)

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import QMessageBox

from .common import PARCEL_MARGIN_FACTOR, log_calls, logFile
from .plan_layout import (
    PlanLayoutCreator,
    MAP_SIDE_MM,
    MARGIN_BOTTOM_MM,
    MARGIN_LEFT_MM,
    MARGIN_RIGHT_MM,
    MARGIN_TOP_MM,
    OVERLAY_PAD_MM,
    PAGE_H_MM,
    PAGE_W_MM,
    TITLE_H_MM,
    NODES_TABLE_HEADER_BG,
    NODES_TABLE_ROW_ALT_BG,
    NODES_TABLE_BORDER_MM,
    NODES_TABLE_ROW_H_MM,
    NODES_TABLE_HEADER_ROW_H_MM,
    NODES_TABLE_TITLE_H_MM,
)


class BoundaryAgreementLayoutCreator(PlanLayoutCreator):
    def __init__(self, iface, parent_group, project, plugin=None):
        super().__init__(iface, parent_group, project, plugin=plugin)
        # Для акту використовуємо окрему групу шарів, але залишаємо fallback на "Кадастровий план"
        # щоб не ламати роботу, якщо групу ще не підготовано.
        self.cadastral_plan_group = (
            parent_group.findGroup("Акт погодження меж")
            or parent_group.findGroup("Кадастровий план")
        )

    def _build_agreement_table_html(
        self,
        font: QFont,
        table_w_mm: float,
        body_row_h_mm: float,
    ) -> Tuple[str, int, float]:
        items = self._build_boundary_description_items()
        if not items:
            return "", 0, 0.0

        def esc(s: str) -> str:
            return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        seg_header = "Частина межі"
        owner_header = "Власник (користувач)"
        sign_header = "Підпис"

        seg_texts = [seg_header] + [f"Від {a} до {b}".strip() for a, b, _, _ in items]
        owner_texts = [owner_header] + [nm or "" for _, _, nm, _ in items]

        pad_mm = 4.0  # 2mm left + 2mm right
        w_seg = max(self._text_width_mm(font, t) for t in seg_texts) + pad_mm
        w_owner = max(self._text_width_mm(font, t) for t in owner_texts) + pad_mm

        w_seg = max(w_seg, 22.0)
        w_owner = max(w_owner, 60.0)

        w_sign = float(table_w_mm) - float(w_seg) - float(w_owner)
        if w_sign < 40.0:
            w_sign = 40.0
            # якщо не влазить, урізаємо owner
            w_owner = max(40.0, float(table_w_mm) - float(w_seg) - float(w_sign))

        table_w_mm = float(w_seg + w_owner + w_sign)

        body_row_h = float(body_row_h_mm)
        tr_body = f"height:{body_row_h:.2f}mm;"
        td_left = f"text-align:left; padding:0 2px; {tr_body} white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"
        td_sign = f"text-align:left; padding:0 2px; {tr_body} white-space:nowrap;"

        tr_head = f"height:{float(NODES_TABLE_HEADER_ROW_H_MM):.2f}mm;"
        th_style = f"font-weight:normal; padding:0 2px; {tr_head} text-align:center;"

        rows_html = []
        rows_html.append(
            f"<tr style='background:{NODES_TABLE_HEADER_BG}; {tr_head}'>"
            f"<th style='{th_style}'>{esc(seg_header)}</th>"
            f"<th style='{th_style}'>{esc(owner_header)}</th>"
            f"<th style='{th_style}'>{esc(sign_header)}</th>"
            "</tr>"
        )

        sign_line = "________________________________________________________________________________"
        # Для збільшення місця під підпис:
        # - перед кожним рядком з даними додаємо "порожній" рядок з пустими комірками
        # - "зебра" не потрібна
        nbsp = "&nbsp;"
        for (a, b, nm, _kn) in items:
            seg = f"Від {a} до {b}".strip()
            rows_html.append(
                f"<tr style='{tr_body}'>"
                f"<td style='{td_left}'>{nbsp}</td>"
                f"<td style='{td_left}'>{nbsp}</td>"
                f"<td style='{td_sign}'>{nbsp}</td>"
                "</tr>"
            )
            rows_html.append(
                f"<tr style='{tr_body}'>"
                f"<td style='{td_left}'>{esc(seg)}</td>"
                f"<td style='{td_left}'>{esc(nm)}</td>"
                f"<td style='{td_sign}'>{esc(sign_line)}</td>"
                "</tr>"
            )

        colgroup = "\n".join(
            [
                f"<col style='width:{float(w_seg):.2f}mm;'>",
                f"<col style='width:{float(w_owner):.2f}mm;'>",
                f"<col style='width:{float(w_sign):.2f}mm;'>",
            ]
        )

        html = f"""
        <div style="width:{float(table_w_mm):.2f}mm; font-size:{float(font.pointSizeF() or 8.0):.2f}pt; font-weight:normal;">
          <table style="
            width:{float(table_w_mm):.2f}mm;
            table-layout:fixed;
            border-collapse:collapse;
            border:{float(NODES_TABLE_BORDER_MM):.2f}mm solid #888;
          ">
            <colgroup>
              {colgroup}
            </colgroup>
            {''.join(rows_html)}
          </table>
        </div>
        """
        # Повертаємо кількість відображуваних рядків (без заголовка)
        return html, len(items) * 2, table_w_mm

    def create_layout(self, scale_value: int):
        if logFile:
            log_calls(logFile, f"create_boundary_agreement_layout scale=1:{int(scale_value)}")

        mgr = self.project.layoutManager()
        name = f"Акт погодження меж {self.parent_group.name()}"

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

        content_x = float(MARGIN_LEFT_MM)
        content_w = float(PAGE_W_MM - MARGIN_LEFT_MM - MARGIN_RIGHT_MM)
        title_y = float(MARGIN_TOP_MM)
        map_y = float(MARGIN_TOP_MM + TITLE_H_MM)

        xml_root = None
        try:
            if self.plugin and getattr(self.plugin, "dockwidget", None):
                xml_data = self.plugin.dockwidget.get_xml_data_for_group(self.parent_group.name())
                if xml_data and getattr(xml_data, "tree", None):
                    xml_root = xml_data.tree.getroot()
        except Exception:
            xml_root = None

        executor_sig_name = self._build_executor_signature_name(xml_root)
        customer_name = self._build_customer_name(xml_root)
        parcel_location = self._build_parcel_location_formatted(xml_root)

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

        # Map
        map_item = QgsLayoutItemMap(layout)
        map_item.setId("Ділянка")
        map_item.setObjectName("Ділянка")
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(content_x, map_y, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(float(MAP_SIDE_MM), float(MAP_SIDE_MM), QgsUnitTypes.LayoutMillimeters))

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

        # Ruler is required for the act (as in cadastral plan)
        try:
            from .ruler import Ruler

            Ruler(layout).add(
                map_x_mm=content_x,
                map_y_mm=map_y,
                map_side_mm=float(MAP_SIDE_MM),
                scale_value=int(scale_value),
            )
        except Exception as e:
            log_calls(logFile, f"Ruler add failed (act): {e}")

        # Title background (same style as cadastral plan)
        title_bg = QgsLayoutItemShape(layout)
        title_bg.setShapeType(QgsLayoutItemShape.Rectangle)
        title_bg.attemptMove(QgsLayoutPoint(content_x, title_y, QgsUnitTypes.LayoutMillimeters))
        title_bg.attemptResize(QgsLayoutSize(content_w, float(TITLE_H_MM), QgsUnitTypes.LayoutMillimeters))
        title_bg_symbol = QgsFillSymbol.createSimple({
            "color": "242,242,242,255",
            "outline_color": "136,136,136,255",
            "outline_width": "0.1",
            "outline_style": "solid",
        })
        title_bg.setSymbol(title_bg_symbol)
        layout.addLayoutItem(title_bg)

        # Title (auto shrink if too many rows)
        items_cnt = 0
        try:
            items_cnt = len(self._build_boundary_description_items())
        except Exception:
            items_cnt = 0

        title_font_pt = 10.0
        if items_cnt >= 18:
            title_font_pt = 9.0
        if items_cnt >= 24:
            title_font_pt = 8.0

        title = QgsLayoutItemLabel(layout)
        title.setText("Акт погодження меж земельної ділянки")
        fnt = QFont()
        fnt.setPointSizeF(float(title_font_pt))
        fnt.setBold(False)
        title.setFont(fnt)
        layout.addLayoutItem(title)
        title.attemptResize(QgsLayoutSize(content_w, float(TITLE_H_MM), QgsUnitTypes.LayoutMillimeters))
        title.setHAlign(Qt.AlignHCenter)
        title.setVAlign(Qt.AlignVCenter)
        title.attemptMove(QgsLayoutPoint(content_x, title_y, QgsUnitTypes.LayoutMillimeters))

        # Neighbor letters (same as cadastral plan)
        try:
            self.add_neighbor_letters(layout, map_item)
        except Exception:
            pass

        # Text block under map
        y_cursor = float(map_y + float(MAP_SIDE_MM) + float(OVERLAY_PAD_MM))

        parts = []
        cust = (customer_name or "").strip()
        if cust:
            parts.append(cust)
        area = (area_ha_txt or "").strip()
        loc = (parcel_location or "").strip()

        txt = "Межа земельної ділянки"
        if parts:
            txt += " " + " ".join(parts)
        if area:
            txt += f" площею {area} га,"
        if loc:
            txt += f" розміщена {loc}"
        txt += " співпадає з існуючою огорожею у наступних частинах:"

        info = QgsLayoutItemLabel(layout)
        info.setText(txt)
        info.setFont(QFont(fnt))
        try:
            info.setWordWrap(True)
        except Exception:
            pass
        layout.addLayoutItem(info)
        info_h = float(NODES_TABLE_TITLE_H_MM) * 3.0
        info.attemptResize(QgsLayoutSize(content_w, info_h, QgsUnitTypes.LayoutMillimeters))
        info.setHAlign(Qt.AlignLeft)
        info.setVAlign(Qt.AlignVCenter)
        info.attemptMove(QgsLayoutPoint(content_x, y_cursor, QgsUnitTypes.LayoutMillimeters))
        y_cursor = float(y_cursor + info_h + 2.0)

        # Boundary table (no extra title, with signature column)
        sig_h = float(TITLE_H_MM)
        sig_y = float(PAGE_H_MM) - float(MARGIN_BOTTOM_MM) - sig_h

        table_font = QFont()
        table_font.setPointSizeF(8.0)

        items_count = 0
        try:
            items_count = len(self._build_boundary_description_items())
        except Exception:
            items_count = 0

        base_row_h = float(NODES_TABLE_ROW_H_MM)
        double_row_h = float(NODES_TABLE_ROW_H_MM) * 2.0
        header_h = float(NODES_TABLE_HEADER_ROW_H_MM)
        available_h = max(0.0, float(sig_y) - float(y_cursor) - 2.0)
        visible_rows = int(items_count) * 2
        desired_h = header_h + float(visible_rows) * double_row_h + 2.0
        body_row_h = double_row_h if (visible_rows > 0 and desired_h <= available_h) else base_row_h

        html, rows, table_w = self._build_agreement_table_html(
            font=table_font, table_w_mm=content_w, body_row_h_mm=body_row_h
        )
        if html and rows:
            tbl = QgsLayoutItemLabel(layout)
            tbl.setMode(QgsLayoutItemLabel.ModeHtml)
            tbl.setText(html)
            try:
                tbl.setFont(QFont(table_font))
            except Exception:
                pass
            tbl.setObjectName("Акт погодження меж:таблиця")
            tbl.setId("Акт погодження меж:таблиця")
            layout.addLayoutItem(tbl)

            tbl_h = float(NODES_TABLE_HEADER_ROW_H_MM) + float(rows) * float(body_row_h) + 2.0
            tbl.attemptResize(QgsLayoutSize(float(table_w), float(tbl_h), QgsUnitTypes.LayoutMillimeters))
            tx = float(content_x) + max(0.0, (float(content_w) - float(table_w)) / 2.0)
            tbl.attemptMove(QgsLayoutPoint(tx, y_cursor, QgsUnitTypes.LayoutMillimeters))

        # Signature (same as cadastral plan)
        sig = QgsLayoutItemLabel(layout)
        sig.setObjectName("Signature")
        sig.setId("Signature")
        sig_text = (
            "Сертифікований інженер-землевпорядник "
            "_____________________________ "
            f"{executor_sig_name}"
        ).rstrip()
        sig.setText(sig_text)
        sig.setFont(QFont(fnt))
        layout.addLayoutItem(sig)
        try:
            sig.setWordWrap(False)
        except Exception:
            pass
        sig.attemptResize(QgsLayoutSize(content_w, sig_h, QgsUnitTypes.LayoutMillimeters))
        sig.setHAlign(Qt.AlignLeft)
        sig.setVAlign(Qt.AlignVCenter)
        sig.attemptMove(QgsLayoutPoint(content_x, sig_y, QgsUnitTypes.LayoutMillimeters))

        return layout
