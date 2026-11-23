"""Regression checks for drift figures produced from other calibrations."""

from importlib.util import find_spec
import unittest

from bell_game_audit.figures import build_chart


@unittest.skipUnless(find_spec("reportlab"), "requires the figures extra")
class DriftFigureTests(unittest.TestCase):
    def test_custom_margins_fit_axes_without_a_crossover(self):
        from reportlab.graphics.charts.lineplots import LinePlot
        from reportlab.graphics.shapes import String

        rows = [
            {"extra_offset_deg": 0, "frozen_worst_gap_pp": 12, "redesigned_worst_gap_pp": 12},
            {"extra_offset_deg": 75, "frozen_worst_gap_pp": -27, "redesigned_worst_gap_pp": -22},
        ]
        chart = build_chart(rows)
        plot = next(item for item in chart.contents if isinstance(item, LinePlot))
        self.assertLess(plot.yValueAxis.valueMin, -27)
        self.assertGreater(plot.yValueAxis.valueMax, 12)
        self.assertEqual(plot.xValueAxis.valueMax, 75)
        labels = [item.text for item in chart.contents if isinstance(item, String)]
        self.assertIn("0", labels)
        self.assertIn("Lowest sampled margins were -27.00 pp for the frozen game "
                      "and -22.00 pp for the redesigned game.", labels)
