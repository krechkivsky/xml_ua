from qgis.core import (
    QgsFillSymbol,
    QgsLayoutItemShape,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsUnitTypes,
)


class Ruler:
    """
    Масштабна лінійка для випадку "розрахункового" (некрасивого) масштабу.

    Малює по нижньому ребру квадрата карти (map_side_mm x map_side_mm) базову
    горизонтальну лінію та вертикальні штрихи через 1 м.
    """

    def __init__(self, layout):
        self.layout = layout

    def add(self, map_x_mm: float, map_y_mm: float, map_side_mm: float, scale_value: int):
        if not self.layout or not scale_value or scale_value <= 0:
            return

        thickness_mm = 0.1


        mm_per_meter = 1000.0 / float(scale_value)
        if mm_per_meter <= 0:
            return

        y_bottom = float(map_y_mm) + float(map_side_mm)


        baseline = QgsLayoutItemShape(self.layout)
        baseline.setShapeType(QgsLayoutItemShape.Rectangle)
        baseline.setId("Ruler:baseline")
        baseline.setObjectName("Ruler:baseline")

        baseline.attemptMove(
            QgsLayoutPoint(float(map_x_mm), y_bottom - thickness_mm, QgsUnitTypes.LayoutMillimeters)
        )
        baseline.attemptResize(
            QgsLayoutSize(float(map_side_mm), thickness_mm, QgsUnitTypes.LayoutMillimeters)
        )
        baseline_symbol = QgsFillSymbol.createSimple(
            {
                "color": "0,0,0,255",
                "outline_style": "no",
            }
        )
        baseline.setSymbol(baseline_symbol)
        self.layout.addLayoutItem(baseline)


        max_meters = int(float(map_side_mm) / mm_per_meter) if mm_per_meter else 0
        for m in range(0, max_meters + 1):
            x = float(map_x_mm) + (m * mm_per_meter)
            if x > float(map_x_mm) + float(map_side_mm):
                break

            if m % 10 == 0:
                tick_h = 3.0
            elif m % 10 == 5:
                tick_h = 2.0
            else:
                tick_h = 1.0

            tick = QgsLayoutItemShape(self.layout)
            tick.setShapeType(QgsLayoutItemShape.Rectangle)
            tick.setId(f"Ruler:tick:{m}")
            tick.setObjectName(f"Ruler:tick:{m}")

            tick.attemptMove(
                QgsLayoutPoint(x, y_bottom - tick_h, QgsUnitTypes.LayoutMillimeters)
            )
            tick.attemptResize(
                QgsLayoutSize(thickness_mm, tick_h, QgsUnitTypes.LayoutMillimeters)
            )
            tick_symbol = QgsFillSymbol.createSimple(
                {
                    "color": "0,0,0,255",
                    "outline_style": "no",
                }
            )
            tick.setSymbol(tick_symbol)
            self.layout.addLayoutItem(tick)
