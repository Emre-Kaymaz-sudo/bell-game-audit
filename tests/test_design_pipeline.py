"""Regression coverage for the in-memory design pipeline and its file adapter."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bell_game_audit.design.search import main as search_main
from bell_game_audit.design.search import search, search_model, search_tables
from bell_game_audit.design.sensitivity import with_extra_offsets
from bell_game_audit.resources import default_model


class DesignPipelineTests(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(default_model.read_text(encoding="utf-8"))

    def test_full_report_uses_the_supplied_calibration_without_mutation(self):
        # A custom name makes silently loading the default model observable.
        self.model["scenarios"][0]["name"] = "custom"
        snapshot = json.dumps(self.model)
        expected = search_model(self.model)
        self.assertEqual(json.dumps(self.model), snapshot)
        self.assertIn("custom", expected["winner"]["scenario_wins"])
        self.assertIn("ideal_reoptimized_win_interval", expected["winner"])
        with TemporaryDirectory() as tmp:
            source, output = Path(tmp, "calibration.json"), Path(tmp, "report.json")
            source.write_text(snapshot, encoding="utf-8")
            self.assertEqual(search(source), expected)
            search_main(["--model", str(source), "--output", str(output)])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), expected)

    def test_drift_is_inclusive_and_preserves_each_input_scenario(self):
        snapshot = json.dumps(self.model)
        scenarios = self.model["scenarios"]
        stressed = with_extra_offsets(self.model, 15)["scenarios"]
        self.assertEqual(len(stressed), 3 * len(scenarios))
        for i, scenario in enumerate(scenarios):
            first, middle, last = scenario["offset_b_deg"]
            for offset, variant in zip((-15, 0, 15), stressed[3*i:3*i+3]):
                self.assertEqual(variant, {
                    **scenario, "name": f"{scenario['name']}_offset_{offset:+d}",
                    "offset_b_deg": [first, middle + offset, last],
                })
        zero = with_extra_offsets(self.model, 0)["scenarios"]
        self.assertEqual([s["name"] for s in zero], [s["name"] + "_offset_+0" for s in scenarios])
        self.assertEqual(json.dumps(self.model), snapshot)

    def test_first_candidate_is_retained_when_many_designs_tie(self):
        scenario = {**self.model["scenarios"][0], "eta_a": [0] * 3, "eta_b": [0] * 3}
        winner = search_tables({**self.model, "scenarios": [scenario]})["winner"]
        self.assertEqual(winner["worst_gap_pp"], 0)
        self.assertEqual(winner["weights"], [[1, 3, 5], [3, 3, 3], [5, 3, 1]])
        self.assertEqual(winner["target_parity"], [[1, 1, 0], [0, 0, 0], [0, 0, 0]])

    def test_small_angular_drift_survives_large_offsets(self):
        self.model["scenarios"][0]["offset_b_deg"][1] = 1e308
        variants = with_extra_offsets(self.model, 5)["scenarios"][:3]
        self.assertEqual([s["offset_b_deg"][1] % 360 for s in variants],
                         [(1e308 % 360 + drift) % 360 for drift in (-5, 0, 5)])

    def test_report_metadata_remains_independent_of_the_source(self):
        self.model["settings"]["notes"] = {"labels": ["calibrated"]}
        self.model["scenarios"][0]["history"] = [{"events": ["initial"]}]
        snapshot = json.dumps(self.model)
        for run in (search_tables, search_model):
            with self.subTest(api=run.__name__):
                report = run(self.model)
                report["settings"]["notes"]["labels"].append("reviewed")
                report["scenarios"][0]["history"][0]["events"].clear()
                report["scenarios"][0]["eta_a"][0] = 0
                self.assertEqual(json.dumps(self.model), snapshot)

    def test_drift_branches_can_be_edited_independently(self):
        self.model["instrument"] = {"channels": [{"name": "B1"}]}
        self.model["scenarios"][0]["history"] = [{"events": ["initial"]}]
        snapshot = json.dumps(self.model)
        branch = with_extra_offsets(self.model, 15)
        separate = with_extra_offsets(self.model, 15)
        separate_snapshot = json.dumps(separate)
        first, second = branch["scenarios"][:2]
        sibling_snapshot = json.dumps(second)
        first["eta_a"][0] = 0
        first["offset_b_deg"][1] = -90
        first["history"][0]["events"].append("changed")
        branch["settings"]["alice_deg"].clear()
        branch["instrument"]["channels"][0]["name"] = "changed"
        self.assertEqual(json.dumps(second), sibling_snapshot)
        self.assertEqual(json.dumps(self.model), snapshot)
        self.assertEqual(json.dumps(separate), separate_snapshot)
