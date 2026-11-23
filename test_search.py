"""Cross-check the finite design space, physical loss convention, and stress sweep."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

import numpy as np

from controls import controls
from run_search import balanced_weights, model_correlations, search_tables
from sensitivity import sweep
from verify_result import verify_result


class InverseDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = json.loads(Path(__file__).with_name("model.json").read_text(encoding="utf-8"))
        cls.result = search_tables(cls.model)

    def test_grid_and_witness(self):
        tables = list(balanced_weights())
        self.assertEqual(len({w.tobytes() for w in tables}), 217)
        for w in tables:
            self.assertTrue((w.sum(axis=0) == 9).all() and (w.sum(axis=1) == 9).all())
            self.assertTrue(((1 <= w) & (w <= 5)).all())
        self.assertEqual(self.result["labelled_candidates"], 217 * 512)
        verify_result(self.result)
        self.assertAlmostEqual(self.result["winner"]["classical_win"], 22 / 27)
        self.assertLess(self.result["best_uniform"]["worst_gap_pp"], 0)
        self.assertGreater(self.result["winner"]["worst_gap_pp"], 2.88)

    def test_loss_model_counts_all_rounds(self):
        blind = deepcopy(self.model)
        for s in blind["scenarios"]:
            s["eta_a"] = s["eta_b"] = [0, 0, 0]
        np.testing.assert_array_equal(model_correlations(blind), 1)
        for s in blind["scenarios"]:
            s["eta_a"] = [1, 1, 1]
        np.testing.assert_array_equal(model_correlations(blind), 0)

    def test_chsh_control_and_angular_stress(self):
        reference = controls(self.result)["best_chsh"]
        self.assertEqual(reference["games_compared"], 72)
        self.assertGreater(reference["worst_gap_pp"], self.result["winner"]["worst_gap_pp"])
        rows = {r["extra_offset_deg"]: r for r in sweep(self.model)}
        self.assertLess(rows[35]["frozen_worst_gap_pp"], 0)
        self.assertGreater(rows[35]["redesigned_worst_gap_pp"], 0)
        self.assertLess(rows[40]["redesigned_worst_gap_pp"], 0)


if __name__ == "__main__":
    unittest.main()
