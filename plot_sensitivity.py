"""Rebuild the fixed-model measurement-drift figure with ReportLab."""

import json
from pathlib import Path

from reportlab.graphics import renderSVG
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors

from sensitivity import sweep


def build_chart(rows):
    d = Drawing(900, 510)
    ink, muted = colors.HexColor("#172e3a"), colors.HexColor("#455a66")
    teal, rust = colors.HexColor("#006e70"), colors.HexColor("#a34122")
    grid, zero = colors.HexColor("#dce3e5"), colors.HexColor("#586d75")

    def label(x, y, words, size=12, color=ink, bold=False, anchor="start"):
        d.add(String(x, y, words, fontName="Helvetica-Bold" if bold else "Helvetica",
                     fontSize=size, fillColor=color, textAnchor=anchor))

    def swatch(x, y, redesigned):
        color = teal if redesigned else rust
        d.add(Line(x, y, x + 34, y, strokeColor=color, strokeWidth=2.4,
                   strokeDashArray=None if redesigned else (7, 4)))
        if redesigned:
            d.add(Circle(x + 17, y, 5, fillColor=colors.white, strokeColor=color, strokeWidth=2))
        else:
            d.add(Rect(x + 14, y - 3, 6, 6, strokeColor=None, fillColor=color))

    d.add(Rect(0, 0, 900, 510, fillColor=colors.white, strokeColor=None))
    label(37, 466, "Robustness to measurement drift", 28, bold=True)
    label(38, 441, "Both games face the same offsets and detector-loss scenarios.", 15, muted)
    label(68, 393, "Worst-case win margin (percentage points)", 13, bold=True)
    swatch(582, 399, True)
    label(624, 395, "Redesigned game", 12)
    swatch(747, 399, False)
    label(789, 395, "Frozen game", 12)

    x, y, width, height = 68, 122, 778, 248
    minimum, maximum = -2.5, 3.25
    px = lambda degrees: x + width * degrees / 45
    py = lambda pp: y + height * (pp - minimum) / (maximum - minimum)

    crossover = next(r for r in rows if r["frozen_worst_gap_pp"] < 0 < r["redesigned_worst_gap_pp"])
    degrees = crossover["extra_offset_deg"]
    d.add(Rect(px(degrees) - 7, y, 14, height, fillColor=colors.HexColor("#edf6f5"), strokeColor=None))
    for tick in range(-2, 4):
        d.add(Line(x, py(tick), x + width, py(tick), strokeColor=zero if tick == 0 else grid,
                   strokeWidth=1.5 if tick == 0 else 0.8))
        label(x - 13, py(tick) - 4, f"{tick:+d}" if tick else "0", 12, muted, anchor="end")
    for row in rows:
        degree = row["extra_offset_deg"]
        label(px(degree), y - 18, str(degree), 12, teal if degree == degrees else muted,
              bold=degree == degrees, anchor="middle")
    label(x + width / 2, y - 42, "Maximum extra offset on Bob's middle setting (degrees)", 13,
          anchor="middle")

    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = x, y, width, height
    plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 0, 45
    plot.yValueAxis.valueMin, plot.yValueAxis.valueMax = minimum, maximum
    plot.xValueAxis.visible = plot.yValueAxis.visible = False
    columns = ("redesigned_worst_gap_pp", "frozen_worst_gap_pp")
    plot.data = [[(r["extra_offset_deg"], r[key]) for r in rows] for key in columns]
    plot.lines[0].strokeColor, plot.lines[1].strokeColor = teal, rust
    plot.lines[0].strokeWidth, plot.lines[1].strokeWidth = 2.6, 2.2
    plot.lines[1].strokeDashArray = [7, 4]
    d.add(plot)
    # A smaller filled square stays visible inside the circle where curves coincide.
    for degree, value in plot.data[0]:
        d.add(Circle(px(degree), py(value), 5, fillColor=colors.white,
                     strokeColor=teal, strokeWidth=2))
    for degree, value in plot.data[1]:
        d.add(Rect(px(degree)-2.75, py(value)-2.75, 5.5, 5.5, fillColor=rust, strokeColor=None))

    d.add(Rect(36, 18, 828, 40, fillColor=colors.HexColor("#edf6f5"), strokeColor=None))
    label(50, 34, f"At {degrees}°", 14, teal, bold=True)
    label(111, 34, f"The frozen game falls to {crossover['frozen_worst_gap_pp']:+.2f} pp. "
          f"The redesigned game retains a {crossover['redesigned_worst_gap_pp']:+.2f} pp margin.", 13)
    return d


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    model = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    result = renderSVG.drawToString(build_chart(sweep(model)))
    result = result.replace("font-family: Helvetica-Bold;", "font-family: Arial, Helvetica, sans-serif; font-weight: 700;")
    result = result.replace("font-family: Helvetica;", "font-family: Arial, Helvetica, sans-serif;")
    result = result.replace("<title>...</title>", "<title>Robustness to measurement drift</title>")
    result = result.replace("<desc>...</desc>",
        "<desc>Worst-case win margins over the classical optimum as the maximum additional "
        "offset of Bob's middle measurement increases. Squares and the dashed line represent "
        "the frozen game. Circles and the solid line represent the redesigned game.</desc>")
    (folder / "drift-sweep.svg").write_text(result, encoding="utf-8", newline="\n")
