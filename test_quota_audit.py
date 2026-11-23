"""Exact reference scores for the referee's scheduling and disclosure rules."""

from collections import Counter
from fractions import Fraction
from itertools import permutations, product
import json
from pathlib import Path
import unittest

from private_history import private_position_bounds
from quota_audit import audit, position_bounds


CHSH = [[0, 0], [0, 1]]


class QuotaAuditTests(unittest.TestCase):
    def test_delayed_disclosure(self):
        weights = [[1, 1], [1, 1]]
        for delay, expected in enumerate((15, 14, 13, 12)):
            with self.subTest(delay=delay):
                before = [Fraction(3, 4)] * (delay + 1)
                after = [Fraction(1)] * (3 - delay)
                scores, mean = private_position_bounds(weights, CHSH, delay)
                self.assertEqual(scores, before + after)
                self.assertEqual(mean, Fraction(expected, 16))
        iid, public = position_bounds(weights, CHSH)
        self.assertEqual(iid, Fraction(3, 4))
        self.assertEqual(public, private_position_bounds(weights, CHSH, 0)[0])

    def test_chsh_unequal_quotas(self):
        # A public CHSH table can lose only on the rarest remaining pair.
        cards = (0, 0, 1, 2, 3)
        orders = set(permutations(cards))
        expected = [Fraction() for _ in cards]
        for deck in orders:
            for t in range(len(deck)):
                tail = deck[t:]
                expected[t] += 1 - Fraction(min(tail.count(i) for i in range(4)), len(tail))
        weights = [[2, 1], [1, 1]]
        iid, public = position_bounds(weights, CHSH)
        self.assertEqual(public, [value / len(orders) for value in expected])
        private, _ = private_position_bounds(weights, CHSH)
        self.assertEqual(private, [iid] * len(cards))

    def test_all_two_by_two_targets_with_private_inputs(self):
        for bits in product((0, 1), repeat=4):
            parity = [list(bits[:2]), list(bits[2:])]
            weights = [[2, 1], [1, 1]]
            expected = Fraction(4, 5) if sum(bits) % 2 else Fraction(1)
            self.assertEqual(private_position_bounds(weights, parity)[1], expected)

    def test_quota_game_and_private_upper_certificate(self):
        result = json.loads(Path(__file__).with_name("result.json").read_text(encoding="utf-8"))
        report = audit(result)
        self.assertEqual(report["iid_classical_win"]["fraction"], "22/27")
        self.assertEqual(report["public_quota_classical_win"]["fraction"], "492544354319/542115674100")
        bounds = report["private_quota_classical_interval"]
        self.assertEqual(bounds["upper"]["fraction"], "22/27")
        self.assertEqual(bounds["rectangle_only_upper"]["fraction"], "8/9")
        weights = result["winner"]["weights"]
        parity = result["winner"]["target_parity"]
        used = Counter()
        for subdeck in bounds["disjoint_chsh_rectangles"]:
            pairs = {tuple(cell) for cell in subdeck}
            xs = {x for x, _ in pairs}
            ys = {y for _, y in pairs}
            self.assertEqual((len(xs), len(ys)), (2, 2))
            self.assertEqual(pairs, set(product(xs, ys)))
            self.assertEqual(sum(parity[x][y] for x, y in pairs) % 2, 1)
            used.update(pairs)
        self.assertTrue(all(n <= weights[x][y] for (x, y), n in used.items()))
        self.assertEqual(len(bounds["disjoint_chsh_rectangles"]), 3)


if __name__ == "__main__":
    unittest.main()
