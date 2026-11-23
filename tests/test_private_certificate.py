"""Check the certificate against actual shuffled decks and independent policies."""

import itertools
import json
import unittest
from collections import Counter, defaultdict
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from bell_game_audit.audit.private_history import private_position_bounds
from bell_game_audit.certificates.build import build, layer_certificate
from bell_game_audit.certificates.verify import verify


ROOT = Path(__file__).resolve().parents[1]


def deterministic_wins(weights, parity):
    """Brute force both players' memoryless one-bit response tables."""
    return max(
        sum(
            weight for x, row in enumerate(weights) for y, weight in enumerate(row)
            if alice[x] ^ bob[y] == parity[x][y]
        )
        for alice in itertools.product(range(2), repeat=len(weights))
        for bob in itertools.product(range(2), repeat=len(weights[0]))
    )


class PrivateCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        winner = json.loads((ROOT / "result.json").read_text(encoding="utf-8"))["winner"]
        cls.weights = winner["weights"]
        cls.parity = winner["target_parity"]
        cls.certificate = json.loads((ROOT / "private_certificate.json").read_text(encoding="utf-8"))

    def test_builder_and_integer_multiple(self):
        certificate, report = build(self.weights, self.parity)
        self.assertEqual(certificate, self.certificate)
        scaled = deepcopy(certificate)
        for part in scaled["components"]:
            part["copies"] *= 100
        weights = [[100 * w for w in row] for row in self.weights]
        rechecked = verify(weights, self.parity, scaled)
        self.assertEqual(rechecked["rounds"], 2700)
        self.assertEqual(rechecked["lower"], report["lower"])
        self.assertEqual(rechecked["upper"], report["upper"])

    def test_full_grid_reproduces_published_counts(self):
        from bell_game_audit.certificates.survey import survey

        result = survey()
        self.assertEqual(result["verified_component_certificates"], 217 * 16)
        self.assertEqual(result["bound_gap_in_wins_histogram"], {"0": 217 * 512})
        self.assertEqual(result, json.loads((ROOT / "private_survey.json").read_text(encoding="utf-8")))

    def test_certificate_matches_memoryless_witness_on_winner(self):
        report = verify(self.weights, self.parity, self.certificate)
        self.assertEqual(deterministic_wins(self.weights, self.parity), 22)
        self.assertEqual(report["rounds"], 27)
        self.assertEqual(report["status"], "exact")
        self.assertEqual(Fraction(report["lower"]), Fraction(22, 27))
        self.assertEqual(Fraction(report["upper"]), Fraction(22, 27))
        total_loss = sum(c["copies"] * c["loss_per_copy"] for c in report["components"])
        self.assertEqual(total_loss, 5)

    def test_rectangular_certificate_with_unused_settings(self):
        weights = [[0, 0, 0], [0, 1, 1], [0, 1, 1], [0, 1, 1]]
        parity = [[0, 0, 0], [0, 0, 0], [0, 0, 1], [0, 0, 1]]
        for deck, target in [(weights, parity), (list(zip(*weights)), list(zip(*parity)))]:
            with self.subTest(rows=len(deck), columns=len(deck[0])):
                report = verify(deck, target, layer_certificate(deck))
                self.assertEqual(deterministic_wins(deck, target), 5)
                self.assertEqual((report["lower"], report["upper"]), ("5/6", "5/6"))

    def test_six_edge_private_prefix_distribution_matches_all_decks(self):
        component = next(c for c in self.certificate["components"] if len(c["actions"]) == 6)
        seed_x, seed_y = component["seed"]
        actions = component["actions"]
        edges = {(g["alice"][seed_x], g["bob"][seed_y]) for g in actions}
        self.assertEqual(len(edges), 6)
        physical = defaultdict(Counter)
        for deck in itertools.permutations(edges):
            for t, (x, y) in enumerate(deck):
                physical[t, x, y][deck[:t]] += 1

        other_actions = [
            g for g in actions if g["alice"] != list(range(len(self.weights)))
            or g["bob"] != list(range(len(self.weights[0])))
        ]
        self.assertEqual(len(other_actions), 5)
        simulated = defaultdict(Counter)
        for shared_order in itertools.permutations(other_actions):
            # Each table is built using only one wing's own question and
            # the same random permutation, before the tables are paired.
            alice_table = {x: tuple(g["alice"][x] for g in shared_order) for x, _ in edges}
            bob_table = {y: tuple(g["bob"][y] for g in shared_order) for _, y in edges}
            for x, y in edges:
                prior = tuple(zip(alice_table[x], bob_table[y]))
                for t in range(6):
                    simulated[t, x, y][prior[:t]] += 1

        self.assertEqual(len(physical), 36)
        for histories in physical.values():
            self.assertEqual(sum(histories.values()), 120)
        self.assertEqual(simulated, physical)

    def test_rejects_mismatched_counts_and_invalid_actions(self):
        bad_weights = deepcopy(self.weights)
        bad_weights[0][0] -= 1
        bad_weights[0][1] += 1
        with self.assertRaises(ValueError):
            verify(bad_weights, self.parity, self.certificate)

        for mutation in ("non_permutation", "duplicate_action", "incomplete"):
            with self.subTest(mutation=mutation):
                bad = deepcopy(self.certificate)
                component = next(c for c in bad["components"] if len(c["actions"]) == 6)
                actions = component["actions"]
                if mutation == "non_permutation":
                    actions[0]["alice"][1] = actions[0]["alice"][0]
                elif mutation == "duplicate_action":
                    actions[1] = deepcopy(actions[0])
                else:
                    del component["seed"]
                with self.assertRaises(ValueError):
                    verify(self.weights, self.parity, bad)

    def test_seed_orbit_alone_cannot_certify_other_current_questions(self):
        identity = {"alice": [0, 1, 2], "bob": [0, 1, 2]}
        rotation = {"alice": [1, 2, 0], "bob": [1, 2, 0]}
        # The maps give both required cards from (0,0), but send (1,1)
        # to (2,2), a card missing from the physical deck.
        certificate = {"version": 1, "components": [
            {"name": "two cards", "copies": 1, "seed": [0, 0], "actions": [identity, rotation]}
        ]}
        weights = [[1, 0, 0], [0, 1, 0], [0, 0, 0]]
        with self.assertRaises(ValueError):
            verify(weights, [[0] * 3 for _ in range(3)], certificate)

    def test_valid_loose_components_do_not_imply_equality(self):
        weights = [[1, 1], [1, 1]]
        parity = [[0, 0], [0, 1]]
        identity = {"alice": [0, 1], "bob": [0, 1]}
        certificate = {
            "version": 1,
            "components": [
                {"name": f"{x},{y}", "copies": 1, "seed": [x, y], "actions": [identity]}
                for x, y in itertools.product(range(2), repeat=2)
            ],
        }
        positions, mean = private_position_bounds(weights, parity)
        self.assertEqual(positions, [Fraction(3, 4)] * 4)
        report = verify(weights, parity, certificate)
        self.assertEqual(report["status"], "interval")
        self.assertEqual(Fraction(report["lower"]), mean)
        self.assertEqual(Fraction(report["upper"]), 1)


if __name__ == "__main__":
    unittest.main()
