import os
from typing import Optional

from qgis.core import (
    QgsFillSymbol,
    QgsLineSymbol,
    QgsLinePatternFillSymbolLayer,
    QgsApplication,
    QgsLayoutItemLabel,
    QgsLayoutItemPicture,
    QgsLayoutItemShape,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsUnitTypes,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
)

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QColor


class Symbols:
    """
    Таблиця "Умовні позначення" для кадастрового плану.

    Вимоги (етап 1):
    - ширина 180 мм, 6 колонок: 20/40/20/40/20/40 мм
    - висота рядка ~15 мм
    - непарні колонки: графічні символи (мініатюри)
    - парні колонки: опис (вирівнювання по лівому краю)
    - перша мініатюра: "ділянка" 12х8 мм з підписами вузлів і довжин сторін
      (реалізовано як міні-map item з шарами підгрупи "Кадастровий план",
       щоб стиль символів автоматично змінювався разом зі стилем шарів).
    """

    COL_W_MM = [20.0, 40.0, 20.0, 40.0, 20.0, 40.0]
    BORDER_MM = 0.0
    TITLE_H_MM = 6.0
    DEMO_W_MM = 12.0 / 1.6
    DEMO_H_MM = 8.0 / 1.6

    def __init__(
        self,
        layout,
        parent_group: Optional[QgsLayerTreeGroup] = None,
        cadastral_plan_group: Optional[QgsLayerTreeGroup] = None,
        xml_root: Optional[object] = None,
    ):
        self.layout = layout
        self.parent_group = parent_group
        self.cadastral_plan_group = cadastral_plan_group
        self.xml_root = xml_root

    def _resolve_source_group(self):
        source_group = None
        if self.parent_group:
            source_group = self._find_group_exact(self.parent_group, "Кадастровий квартал")
        if not source_group:
            source_group = self.cadastral_plan_group
        if not source_group:
            source_group = self.parent_group
        return source_group

    def _find_group_exact(self, group: QgsLayerTreeGroup, name: str):
        if not group:
            return None
        for ch in group.children():
            if isinstance(ch, QgsLayerTreeGroup) and ch.name().lower() == name.lower():
                return ch
            if isinstance(ch, QgsLayerTreeGroup):
                r = self._find_group_exact(ch, name)
                if r:
                    return r
        return None

    def _find_layer_exact(self, group: QgsLayerTreeGroup, name: str):
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

    def _find_layer_from_sources(self, name: str):

        if self.parent_group:
            quarter = self._find_group_exact(self.parent_group, "Кадастровий квартал")
            lyr = self._find_layer_exact(quarter, name) if quarter else None
            if lyr:
                return lyr
        lyr = self._find_layer_exact(self.cadastral_plan_group, name) if self.cadastral_plan_group else None
        if lyr:
            return lyr
        lyr = self._find_layer_exact(self.parent_group, name) if self.parent_group else None
        return lyr

    def _clone_renderer_symbol(self, layer):
        if not layer:
            return None
        try:
            renderer = layer.renderer() if hasattr(layer, "renderer") else None
            base_symbol = renderer.symbol() if renderer else None
            return base_symbol.clone() if base_symbol else None
        except Exception:
            return None

    def _restriction_code_from_xml(self, object_id: str) -> str:
        if not self.xml_root or not object_id:
            return ""
        try:
            oid = str(object_id).strip()
            if not oid:
                return ""
            res = self.xml_root.xpath(
                "//*[local-name()='RestrictionInfo'][@object_id=$oid]"
                "/*[local-name()='RestrictionCode'][1]/text()",
                oid=oid,
            )
            if not res:
                return ""
            return str(res[0]).strip()
        except Exception:
            return ""

    def _make_restriction_hatch_symbol(self, angle_deg: float) -> QgsFillSymbol:
        """
        Hatch fill for restrictions:
        - angle: 15 + object_id * 35 (deg)
        - line width: 0.1 mm
        - line color: black
        - spacing: 3 mm
        """
        def _outline_like_cell3() -> dict:

            defaults = {
                "outline_color": "0,0,0,255",
                "outline_width": "0.3",
                "outline_style": "solid",
                "outline_width_unit": "MM",
            }
            try:
                lyr = self._find_layer_from_sources("Угіддя")
                sym = self._clone_renderer_symbol(lyr)
                if not sym or not isinstance(sym, QgsFillSymbol):
                    return defaults
                sl = sym.symbolLayer(0) if hasattr(sym, "symbolLayer") else None
                props = sl.properties() if sl and hasattr(sl, "properties") else {}
                if not isinstance(props, dict):
                    return defaults
                out = dict(defaults)
                for k in ("outline_color", "outline_width", "outline_style", "outline_width_unit"):
                    v = props.get(k)
                    if v not in (None, ""):
                        out[k] = v
                return out
            except Exception:
                return defaults

        try:
            outline = _outline_like_cell3()
            fill = QgsFillSymbol.createSimple({"color": "255,255,255,0", **outline})



            pattern = None
            try:
                if hasattr(QgsLinePatternFillSymbolLayer, "create"):
                    pattern = QgsLinePatternFillSymbolLayer.create(
                        {
                            "angle": str(float(angle_deg)),
                            "distance": "3",
                            "distance_unit": "MM",
                            "line_width": "0.1",
                            "line_width_unit": "MM",
                            "color": "0,0,0,255",
                        }
                    )
            except Exception:
                pattern = None
            if pattern is not None:
                try:
                    if hasattr(pattern, "setLineAngle"):
                        pattern.setLineAngle(float(angle_deg))
                    elif hasattr(pattern, "setAngle"):
                        pattern.setAngle(float(angle_deg))
                except Exception:
                    pass

            if pattern is None:
                pattern = QgsLinePatternFillSymbolLayer()
                try:
                    if hasattr(pattern, "setLineAngle"):
                        pattern.setLineAngle(float(angle_deg))
                    elif hasattr(pattern, "setAngle"):
                        pattern.setAngle(float(angle_deg))
                except Exception:
                    pass
                try:
                    if hasattr(pattern, "setDistance"):
                        pattern.setDistance(3.0)
                except Exception:
                    pass
                try:
                    if hasattr(pattern, "setLineWidth"):
                        pattern.setLineWidth(0.1)
                except Exception:
                    pass
                try:
                    if hasattr(pattern, "setColor"):
                        pattern.setColor(QColor(0, 0, 0))
                except Exception:
                    pass
                try:
                    if hasattr(pattern, "setDistanceUnit"):
                        pattern.setDistanceUnit(QgsUnitTypes.RenderMillimeters)
                except Exception:
                    pass
                try:
                    if hasattr(pattern, "setLineWidthUnit"):
                        pattern.setLineWidthUnit(QgsUnitTypes.RenderMillimeters)
                except Exception:
                    pass


            try:
                line_sym = QgsLineSymbol.createSimple(
                    {
                        "line_color": "0,0,0,255",
                        "line_style": "solid",
                        "line_width": "0.1",
                        "line_width_unit": "MM",
                    }
                )
                if hasattr(pattern, "setSubSymbol"):
                    pattern.setSubSymbol(line_sym)
            except Exception:
                pass

            try:
                fill.appendSymbolLayer(pattern)
            except Exception:
                return QgsFillSymbol.createSimple({"color": "255,255,255,0", **outline})
            return fill
        except Exception:
            return QgsFillSymbol.createSimple({"color": "255,255,255,0", **_outline_like_cell3()})

    def _add_demo_restriction_rect(self, x_mm: float, y_mm: float, w_mm: float, h_mm: float, object_id: int):
        angle = (15.0 + float(object_id) * 35.0) % 360.0
        rect = QgsLayoutItemShape(self.layout)
        rect.setShapeType(QgsLayoutItemShape.Rectangle)
        rect.setId(f"Symbols:restriction_demo:{object_id}")
        rect.setObjectName(f"Symbols:restriction_demo:{object_id}")
        rect.attemptMove(QgsLayoutPoint(float(x_mm), float(y_mm), QgsUnitTypes.LayoutMillimeters))
        rect.attemptResize(QgsLayoutSize(float(w_mm), float(h_mm), QgsUnitTypes.LayoutMillimeters))
        rect.setSymbol(self._make_restriction_hatch_symbol(angle))
        self.layout.addLayoutItem(rect)
        return rect

    def _add_cell_rect(self, x_mm: float, y_mm: float, w_mm: float, h_mm: float, obj_id: str):
        rect = QgsLayoutItemShape(self.layout)
        rect.setShapeType(QgsLayoutItemShape.Rectangle)
        rect.setId(obj_id)
        rect.setObjectName(obj_id)
        rect.attemptMove(QgsLayoutPoint(x_mm, y_mm, QgsUnitTypes.LayoutMillimeters))
        rect.attemptResize(QgsLayoutSize(w_mm, h_mm, QgsUnitTypes.LayoutMillimeters))
        sym = QgsFillSymbol.createSimple(
            {
                "color": "255,255,255,0",
                "outline_style": "no",
            }
        )
        rect.setSymbol(sym)
        self.layout.addLayoutItem(rect)
        return rect

    def _add_text(
        self,
        text: str,
        x_mm: float,
        y_mm: float,
        w_mm: float,
        h_mm: float,
        align: Qt.AlignmentFlag,
        font_pt: float = 8.0,
    ):
        lbl = QgsLayoutItemLabel(self.layout)
        lbl.setText(text)
        f = QFont()
        f.setPointSizeF(float(font_pt))
        f.setBold(False)
        lbl.setFont(f)
        try:
            lbl.setWordWrap(True)
        except Exception:
            pass
        self.layout.addLayoutItem(lbl)
        lbl.attemptResize(QgsLayoutSize(w_mm, h_mm, QgsUnitTypes.LayoutMillimeters))
        lbl.setHAlign(align)
        lbl.setVAlign(Qt.AlignVCenter)
        lbl.attemptMove(QgsLayoutPoint(x_mm, y_mm, QgsUnitTypes.LayoutMillimeters))
        return lbl

    def _add_demo_fill_rect(self, layer_name: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float, obj_id: str):
        lyr = self._find_layer_from_sources(layer_name)
        rect = QgsLayoutItemShape(self.layout)
        rect.setShapeType(QgsLayoutItemShape.Rectangle)
        rect.setId(obj_id)
        rect.setObjectName(obj_id)
        rect.attemptMove(QgsLayoutPoint(float(x_mm), float(y_mm), QgsUnitTypes.LayoutMillimeters))
        rect.attemptResize(QgsLayoutSize(float(w_mm), float(h_mm), QgsUnitTypes.LayoutMillimeters))

        symbol = self._clone_renderer_symbol(lyr)
        if symbol is None or not isinstance(symbol, QgsFillSymbol):
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": "255,255,255,0",
                    "outline_color": "0,0,0,255",
                    "outline_width": "0.3",
                    "outline_style": "solid",
                }
            )

        rect.setSymbol(symbol)
        self.layout.addLayoutItem(rect)
        return rect

    def _add_demo_line_with_arrows(self, layer_name: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float):




        lyr = self._find_layer_from_sources(layer_name)
        line_symbol = self._clone_renderer_symbol(lyr)
        try:
            line_color = line_symbol.color().name() if line_symbol else "#000000"
        except Exception:
            line_color = "#000000"


        seg_w = 0.2
        seg_h = float(self.DEMO_H_MM) + 2.0

        cx = float(x_mm) + float(w_mm) / 2.0
        cy = float(y_mm) + float(h_mm) / 2.0
        seg_x = cx - seg_w / 2.0
        seg_y = cy - seg_h / 2.0

        base = QgsLayoutItemShape(self.layout)
        base.setShapeType(QgsLayoutItemShape.Rectangle)
        base.setId("Symbols:adj_line_v")
        base.setObjectName("Symbols:adj_line_v")
        base.attemptMove(QgsLayoutPoint(seg_x, seg_y, QgsUnitTypes.LayoutMillimeters))
        base.attemptResize(QgsLayoutSize(seg_w, seg_h, QgsUnitTypes.LayoutMillimeters))
        base.setSymbol(QgsFillSymbol.createSimple({"color": line_color, "outline_style": "no"}))
        self.layout.addLayoutItem(base)

        def _find_arrow_svg() -> str:
            rel = os.path.join("arrows", "Arrow_05.svg")
            try:
                for base_dir in QgsApplication.svgPaths() or []:
                    cand = os.path.join(base_dir, rel)
                    if os.path.exists(cand):
                        return cand
            except Exception:
                pass
            return ""

        arrow_svg = _find_arrow_svg()

        ah = 2.0 * 0.8
        aw = 2.0 * 0.8
        arrow_x = cx - aw / 2.0

        arrow_y = seg_y - ah + 1.0

        if arrow_svg:
            pic = QgsLayoutItemPicture(self.layout)
            pic.setId("Symbols:adj_arrow_top")
            pic.setObjectName("Symbols:adj_arrow_top")
            pic.setPicturePath(arrow_svg)
            self.layout.addLayoutItem(pic)
            pic.attemptResize(QgsLayoutSize(aw, ah, QgsUnitTypes.LayoutMillimeters))
            pic.attemptMove(QgsLayoutPoint(arrow_x, arrow_y, QgsUnitTypes.LayoutMillimeters))

            try:
                black = QColor(0, 0, 0)
                if hasattr(pic, "setSvgFillColor"):
                    pic.setSvgFillColor(black)
                if hasattr(pic, "setSvgStrokeColor"):
                    pic.setSvgStrokeColor(black)
            except Exception:
                pass

        lbl = QgsLayoutItemLabel(self.layout)
        lbl.setId("Symbols:adj_arrow_lbl_a")
        lbl.setObjectName("Symbols:adj_arrow_lbl_a")
        lbl.setText("А")
        f = QFont()
        f.setPointSizeF(7.0)
        f.setBold(False)
        lbl.setFont(f)
        self.layout.addLayoutItem(lbl)
        lbl_w = 4.0
        lbl_h = 3.0
        lbl.attemptResize(QgsLayoutSize(lbl_w, lbl_h, QgsUnitTypes.LayoutMillimeters))
        lbl.setHAlign(Qt.AlignLeft)
        lbl.setVAlign(Qt.AlignVCenter)
        lbl_x = cx + aw / 2.0 + 0.5
        lbl_y = (arrow_y + ah / 2.0) - (lbl_h / 2.0)
        lbl.attemptMove(QgsLayoutPoint(lbl_x, lbl_y, QgsUnitTypes.LayoutMillimeters))

    def _add_demo_point(self, layer_name: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float):

        lyr = self._find_layer_from_sources(layer_name)
        sym = self._clone_renderer_symbol(lyr)
        try:
            color = sym.color().name() if sym and hasattr(sym, "color") else "#000000"
        except Exception:
            color = "#000000"


        d = min(float(w_mm), float(h_mm), 3.0) * 0.75
        cx = float(x_mm) + (float(w_mm) - d) / 2.0
        cy = float(y_mm) + (float(h_mm) - d) / 2.0

        dot = QgsLayoutItemShape(self.layout)
        try:
            dot.setShapeType(QgsLayoutItemShape.Ellipse)
        except Exception:
            dot.setShapeType(QgsLayoutItemShape.Rectangle)
        dot.setId("Symbols:control_point")
        dot.setObjectName("Symbols:control_point")
        dot.attemptMove(QgsLayoutPoint(cx, cy, QgsUnitTypes.LayoutMillimeters))
        dot.attemptResize(QgsLayoutSize(d, d, QgsUnitTypes.LayoutMillimeters))
        dot.setSymbol(QgsFillSymbol.createSimple({"color": color, "outline_style": "no"}))
        self.layout.addLayoutItem(dot)

    def _add_number_in_circle(self, text: str, cx_mm: float, cy_mm: float, diameter_mm: float = 3.0):
        d = float(diameter_mm)
        x = float(cx_mm) - d / 2.0
        y = float(cy_mm) - d / 2.0

        circle = QgsLayoutItemShape(self.layout)
        try:
            circle.setShapeType(QgsLayoutItemShape.Ellipse)
        except Exception:
            circle.setShapeType(QgsLayoutItemShape.Rectangle)
        circle.setId("Symbols:lands_num_circle")
        circle.setObjectName("Symbols:lands_num_circle")
        circle.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        circle.attemptResize(QgsLayoutSize(d, d, QgsUnitTypes.LayoutMillimeters))
        circle.setSymbol(
            QgsFillSymbol.createSimple(
                {
                    "color": "255,255,255,0",
                    "outline_color": "0,0,0,255",
                    "outline_width": "0.1",
                    "outline_style": "solid",
                }
            )
        )
        self.layout.addLayoutItem(circle)

        lbl = QgsLayoutItemLabel(self.layout)
        lbl.setText(str(text))
        f = QFont()
        f.setPointSizeF(6.0)
        f.setBold(False)
        lbl.setFont(f)
        try:
            lbl.setWordWrap(False)
        except Exception:
            pass
        self.layout.addLayoutItem(lbl)
        lbl.attemptResize(QgsLayoutSize(d, d, QgsUnitTypes.LayoutMillimeters))
        lbl.setHAlign(Qt.AlignHCenter)
        lbl.setVAlign(Qt.AlignVCenter)
        lbl.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        return circle, lbl

    def _add_demo_parcel(self, cell_x_mm: float, cell_y_mm: float, cell_w_mm: float, cell_h_mm: float):

        mini_w = self.DEMO_W_MM
        mini_h = self.DEMO_H_MM
        mini_x = cell_x_mm + (cell_w_mm - mini_w) / 2.0
        mini_y = cell_y_mm + (cell_h_mm - mini_h) / 2.0

        rect = self._add_demo_fill_rect(
            layer_name="Ділянка",
            x_mm=mini_x,
            y_mm=mini_y,
            w_mm=mini_w,
            h_mm=mini_h,
            obj_id="Symbols:parcel_demo",
        )



        font = QFont()
        font.setPointSizeF(5.0)
        font.setBold(False)

        def _label(text: str, x: float, y: float, w: float, h: float, halign: Qt.AlignmentFlag):
            lbl = QgsLayoutItemLabel(self.layout)
            lbl.setText(text)
            lbl.setFont(font)
            self.layout.addLayoutItem(lbl)
            lbl.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
            lbl.setHAlign(halign)
            lbl.setVAlign(Qt.AlignVCenter)
            lbl.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
            return lbl

        pad = 0.3
        label_w = 2.2
        label_h = 2.0


        _label("1", mini_x + pad, mini_y + pad, label_w, label_h, Qt.AlignLeft)
        _label("2", mini_x + mini_w - label_w - pad, mini_y + pad, label_w, label_h, Qt.AlignRight)
        _label("3", mini_x + mini_w - label_w - pad, mini_y + mini_h - label_h - pad, label_w, label_h, Qt.AlignRight)
        _label("4", mini_x + pad, mini_y + mini_h - label_h - pad, label_w, label_h, Qt.AlignLeft)


        len_w = 6.5
        len_h = 2.0
        _label("10.00", mini_x + (mini_w - len_w) / 2.0, mini_y - len_h - 0.2, len_w, len_h, Qt.AlignHCenter)
        _label("8.00", mini_x + mini_w + 0.2, mini_y + (mini_h - len_h) / 2.0, len_w, len_h, Qt.AlignLeft)
        _label("10.00", mini_x + (mini_w - len_w) / 2.0, mini_y + mini_h + 0.2, len_w, len_h, Qt.AlignHCenter)
        _label("8.00", mini_x - len_w - 0.2, mini_y + (mini_h - len_h) / 2.0, len_w, len_h, Qt.AlignRight)

        return rect

    def add(self, x_mm: float, y_mm: float, table_w_mm: float, row_h_mm: float = 15.0):
        if not self.layout:
            return


        title_rect = self._add_cell_rect(
            x_mm,
            y_mm,
            table_w_mm,
            self.TITLE_H_MM,
            obj_id="Symbols:title_bg",
        )

        try:
            title_sym = QgsFillSymbol.createSimple(
                {
                    "color": "255,255,255,0",
                    "outline_style": "no",
                }
            )
            title_rect.setSymbol(title_sym)
        except Exception:
            pass

        title_lbl = QgsLayoutItemLabel(self.layout)
        title_lbl.setText("Умовні позначення")
        f = QFont()
        f.setPointSizeF(9)
        f.setBold(False)
        title_lbl.setFont(f)
        self.layout.addLayoutItem(title_lbl)
        title_lbl.attemptResize(QgsLayoutSize(table_w_mm, self.TITLE_H_MM, QgsUnitTypes.LayoutMillimeters))
        title_lbl.setHAlign(Qt.AlignHCenter)
        title_lbl.setVAlign(Qt.AlignVCenter)
        title_lbl.attemptMove(QgsLayoutPoint(x_mm, y_mm, QgsUnitTypes.LayoutMillimeters))


        row_y = y_mm + self.TITLE_H_MM
        pad = 1.0

        def _row_cells(r: int, y0: float):
            cur_x = x_mm
            for col_idx, w in enumerate(self.COL_W_MM, 1):
                self._add_cell_rect(
                    cur_x,
                    y0,
                    w,
                    row_h_mm,
                    obj_id=f"Symbols:cell:r{r}:c{col_idx}",
                )
                cur_x += w


        _row_cells(1, row_y)
        self._add_demo_parcel(x_mm, row_y, self.COL_W_MM[0], row_h_mm)
        self._add_text(
            "Ділянка з номерами вершин і довжинами сторін",
            x_mm + self.COL_W_MM[0] + pad,
            row_y,
            self.COL_W_MM[1] - 2 * pad,
            row_h_mm,
            align=Qt.AlignLeft,
            font_pt=6.0,
        )


        c3_x = x_mm + sum(self.COL_W_MM[:2])
        mini_x = c3_x + (self.COL_W_MM[2] - self.DEMO_W_MM) / 2.0
        mini_y = row_y + (row_h_mm - self.DEMO_H_MM) / 2.0
        self._add_demo_fill_rect("Угіддя", mini_x, mini_y, self.DEMO_W_MM, self.DEMO_H_MM, "Symbols:lands_demo")
        self._add_number_in_circle(
            "1",
            cx_mm=mini_x + self.DEMO_W_MM / 2.0,
            cy_mm=mini_y + self.DEMO_H_MM / 2.0,
            diameter_mm=3.0,
        )
        self._add_text(
            "Угіддя ділянки з номером угіддя",
            c3_x + self.COL_W_MM[2] + pad,
            row_y,
            self.COL_W_MM[3] - 2 * pad,
            row_h_mm,
            align=Qt.AlignLeft,
            font_pt=6.0,
        )


        c5_x = x_mm + sum(self.COL_W_MM[:4])
        mini_x = c5_x + (self.COL_W_MM[4] - self.DEMO_W_MM) / 2.0
        mini_y = row_y + (row_h_mm - self.DEMO_H_MM) / 2.0
        self._add_demo_fill_rect("Оренда", mini_x, mini_y, self.DEMO_W_MM, self.DEMO_H_MM, "Symbols:lease_demo")
        self._add_text(
            "Частина ділянки, передана в оренду",
            c5_x + self.COL_W_MM[4] + pad,
            row_y,
            self.COL_W_MM[5] - 2 * pad,
            row_h_mm,
            align=Qt.AlignLeft,
            font_pt=6.0,
        )


        row2_y = row_y + row_h_mm
        _row_cells(2, row2_y)


        c7_x = x_mm
        mini_x = c7_x + (self.COL_W_MM[0] - self.DEMO_W_MM) / 2.0
        mini_y = row2_y + (row_h_mm - self.DEMO_H_MM) / 2.0
        self._add_demo_fill_rect("Суборенда", mini_x, mini_y, self.DEMO_W_MM, self.DEMO_H_MM, "Symbols:sublease_demo_1")

        self._add_demo_fill_rect("Суборенда", mini_x, mini_y, self.DEMO_W_MM, self.DEMO_H_MM, "Symbols:sublease_demo_2")
        self._add_text(
            "Частина орендованої ділянки, передана в суборенду",
            c7_x + self.COL_W_MM[0] + pad,
            row2_y,
            self.COL_W_MM[1] - 2 * pad,
            row_h_mm,
            align=Qt.AlignLeft,
            font_pt=6.0,
        )


        c9_x = x_mm + sum(self.COL_W_MM[:2])
        self._add_demo_line_with_arrows("Суміжники", c9_x, row2_y, self.COL_W_MM[2], row_h_mm)
        self._add_text(
            "Межа суміжної ділянки",
            c9_x + self.COL_W_MM[2] + pad,
            row2_y,
            self.COL_W_MM[3] - 2 * pad,
            row_h_mm,
            align=Qt.AlignLeft,
            font_pt=6.0,
        )


        c11_x = x_mm + sum(self.COL_W_MM[:4])
        self._add_demo_point("Закріплені вузли", c11_x, row2_y, self.COL_W_MM[4], row_h_mm)
        self._add_text(
            "Закріплені вузли межі полігона ділянки",
            c11_x + self.COL_W_MM[4] + pad,
            row2_y,
            self.COL_W_MM[5] - 2 * pad,
            row_h_mm,
            align=Qt.AlignLeft,
            font_pt=6.0,
        )




        restrictions_layer = None
        try:
            if self.cadastral_plan_group:
                restrictions_layer = self._find_layer_exact(self.cadastral_plan_group, "Обмеження")
        except Exception:
            restrictions_layer = None
        if restrictions_layer is None:
            restrictions_layer = self._find_layer_from_sources("Обмеження")

        restrictions = []
        if restrictions_layer is not None:
            try:
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
                        try:
                            oid = ftr.attribute("object_id")
                        except Exception:
                            oid = None
                    if oid is None:
                        continue
                    try:
                        oid_int = int(str(oid).strip())
                    except Exception:
                        continue

                    code = ""
                    try:
                        code = str(ftr["RestrictionCode"] or "").strip()
                    except Exception:
                        code = ""
                    if not code:
                        code = self._restriction_code_from_xml(str(oid_int))
                    restrictions.append((oid_int, code))
            except Exception:
                restrictions = []


        if restrictions:
            seen = set()
            uniq = []
            for oid_int, code in restrictions:
                if oid_int in seen:
                    continue
                seen.add(oid_int)
                uniq.append((oid_int, code))
            restrictions = uniq


        if restrictions:
            start_y = row_y + 2 * row_h_mm
            pairs_per_row = 3
            for idx, (oid_int, code) in enumerate(restrictions):
                r = idx // pairs_per_row  # 0-based extra row index
                pos = idx % pairs_per_row  # 0..2
                y0 = start_y + r * row_h_mm


                if pos == 0:
                    _row_cells(3 + r, y0)

                col_sym = 2 * pos  # 0,2,4
                cell_x = x_mm + sum(self.COL_W_MM[:col_sym])
                cell_w = self.COL_W_MM[col_sym]
                text_x = cell_x + cell_w
                text_w = self.COL_W_MM[col_sym + 1]

                mini_x = cell_x + (cell_w - self.DEMO_W_MM) / 2.0
                mini_y = y0 + (row_h_mm - self.DEMO_H_MM) / 2.0
                self._add_demo_restriction_rect(mini_x, mini_y, self.DEMO_W_MM, self.DEMO_H_MM, oid_int)

                code_txt = (
                    f"Частина земельної ділянки з обмеженнями у використанні (код обмеження {code})"
                    if code
                    else "Частина земельної ділянки з обмеженням"
                )
                self._add_text(
                    code_txt,
                    text_x + pad,
                    y0,
                    text_w - 2 * pad,
                    row_h_mm,
                    align=Qt.AlignLeft,
                    font_pt=6.0,
                )
