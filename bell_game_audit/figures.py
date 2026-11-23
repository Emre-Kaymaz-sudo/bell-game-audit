"""Rebuild the fixed-model measurement-drift figure with ReportLab."""

import argparse
import math
from pathlib import Path

from .design.sensitivity import sweep
from .resources import default_model, read_model


def build_chart(rows):
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
    from reportlab.lib import colors

    rows = sorted(rows, key=lambda row: row["extra_offset_deg"])
    if not rows:
        raise ValueError("the drift chart requires at least one sampled offset")
    columns = ("redesigned_worst_gap_pp", "frozen_worst_gap_pp")
    series = [[(row["extra_offset_deg"], row[key]) for row in rows] for key in columns]
    margins = [margin for curve in series for _, margin in curve]
    # Keep a common frame around zero for small changes, expanding it for
    # calibrations with larger losses or advantages.
    lowest, highest = min(margins), max(margins)
    padding = max(0.25, 0.04 * (max(0, highest) - min(0, lowest)))
    minimum = min(-2.5, lowest - padding)
    maximum = max(3.25, highest + padding)
    tick_step = max(1, math.ceil((maximum - minimum) / 7))
    ticks = range(math.ceil(minimum / tick_step) * tick_step, math.floor(maximum) + 1, tick_step)
    max_offset = max(1, rows[-1]["extra_offset_deg"])
    crossover = next((row for row in rows
                      if row["frozen_worst_gap_pp"] < 0 < row["redesigned_worst_gap_pp"]), None)
    crossover_offset = crossover["extra_offset_deg"] if crossover else None

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
    def px(degrees):
        return x + width * degrees / max_offset

    def py(pp):
        return y + height * (pp - minimum) / (maximum - minimum)

    if crossover is not None:
        d.add(Rect(px(crossover_offset) - 7, y, 14, height,
                   fillColor=colors.HexColor("#edf6f5"), strokeColor=None))
    for tick in ticks:
        d.add(Line(x, py(tick), x + width, py(tick), strokeColor=zero if tick == 0 else grid,
                   strokeWidth=1.5 if tick == 0 else 0.8))
        label(x - 13, py(tick) - 4, f"{tick:+d}" if tick else "0", 12, muted, anchor="end")
    for row in rows:
        degree = row["extra_offset_deg"]
        label(px(degree), y - 18, str(degree), 12, teal if degree == crossover_offset else muted,
              bold=degree == crossover_offset, anchor="middle")
    label(x + width / 2, y - 42, "Maximum extra offset on Bob's middle setting (degrees)", 13,
          anchor="middle")

    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = x, y, width, height
    plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 0, max_offset
    plot.yValueAxis.valueMin, plot.yValueAxis.valueMax = minimum, maximum
    plot.xValueAxis.visible = plot.yValueAxis.visible = False
    plot.data = series
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
    if crossover is not None:
        label(50, 34, f"At {crossover_offset}°", 14, teal, bold=True)
        label(111, 34, f"The frozen game falls to {crossover['frozen_worst_gap_pp']:+.2f} pp. "
              f"The redesigned game retains a {crossover['redesigned_worst_gap_pp']:+.2f} pp margin.", 13)
    else:
        frozen_min = min(row["frozen_worst_gap_pp"] for row in rows)
        redesigned_min = min(row["redesigned_worst_gap_pp"] for row in rows)
        label(50, 34, f"Lowest sampled margins were {frozen_min:+.2f} pp for the frozen game "
              f"and {redesigned_min:+.2f} pp for the redesigned game.", 13)
    return d


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--model", type=Path, default=default_model)
    parser.add_argument("--output", type=Path, default=Path("drift-sweep.svg"))
    args = parser.parse_args(argv)
    try:
        from reportlab.graphics import renderSVG
    except ModuleNotFoundError as error:
        if error.name != "reportlab":
            raise
        parser.error('install the plotting extra with python -m pip install ".[figures]" from the checkout')
    model = read_model(args.model)
    result = renderSVG.drawToString(build_chart(sweep(model)))
    result = result.replace("font-family: Helvetica-Bold;", "font-family: Arial, Helvetica, sans-serif; font-weight: 700;")
    result = result.replace("font-family: Helvetica;", "font-family: Arial, Helvetica, sans-serif;")
    result = result.replace("<title>...</title>", "<title>Robustness to measurement drift</title>")
    result = result.replace("<desc>...</desc>",
        "<desc>Worst-case win margins over the classical optimum as the maximum additional "
        "offset of Bob's middle measurement increases. Squares and the dashed line represent "
        "the frozen game. Circles and the solid line represent the redesigned game.</desc>")
    args.output.write_text(result, encoding="utf-8", newline="\n")
