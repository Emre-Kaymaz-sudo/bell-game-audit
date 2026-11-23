"""Cross-check the finite design space, physical loss convention, and stress sweep."""

from copy import deepcopy
import json
import unittest

import numpy as np

from bell_game_audit.resources import default_model
from bell_game_audit.design.controls import controls
from bell_game_audit.design.search import balanced_weights, model_correlations, search_tables
from bell_game_audit.design.sensitivity import sweep
from bell_game_audit.design.verify import verify_result


class InverseDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = json.loads(default_model.read_text(encoding="utf-8"))
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

    def test_search_rejects_calibrations_the_witness_verifier_cannot_replay(self):
        scenario = self.model["scenarios"][0]
        for field, value in (("name", " "), ("name", 1), ("visibility", True),
                             ("visibility", "0.99"), ("eta_a", [1, True, 1]),
                             ("offset_b_deg", [0, "1", 0])):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                search_tables({**self.model, "scenarios": [{**scenario, field: value}]})

    def test_large_angles_preserve_full_turn_symmetry(self):
        model = deepcopy(self.model)
        model["settings"]["alice_deg"][0] = 10**400 + 137
        model["settings"]["bob_deg"][2] = 1e308
        model["scenarios"][0]["offset_b_deg"][2] = 1e308
        reduced = deepcopy(model)
        reduced["settings"]["alice_deg"][0] %= 360
        reduced["settings"]["bob_deg"][2] %= 360
        reduced["scenarios"][0]["offset_b_deg"][2] %= 360
        np.testing.assert_array_equal(model_correlations(model), model_correlations(reduced))
        verify_result(search_tables(model))

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
