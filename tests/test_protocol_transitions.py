"""Exercise the referee's deterministic transition without a random source."""

import unittest
from collections import Counter
from dataclasses import FrozenInstanceError

from bell_game_audit.protocol.referee import _DrawState, _Game


class DrawTransitionTests(unittest.TestCase):
    def test_validated_game_is_independent_of_callers_matrices(self):
        weights = [[1, 2, 1], [2, 1, 2]]
        targets = [[0, 1, 0], [1, 0, 1]]
        game = _Game.from_matrices(weights, targets)
        weights[0][0] = targets[1][2] = 42
        self.assertEqual(game.boundaries, (1, 3, 4, 6, 7, 9))
        self.assertEqual(game.targets, ((0, 1, 0), (1, 0, 1)))
        with self.assertRaises(FrozenInstanceError):
            game.boundaries = ()
        for bad_weights, bad_targets in [
            ([[1], [2, 3]], [[0], [0, 1]]),
            ([[True]], [[0]]),
            ([[1]], [[False]]),
            ([[1, 2]], [[1]]),
        ]:
            with self.subTest(weights=bad_weights, targets=bad_targets), self.assertRaises(ValueError):
                _Game.from_matrices(bad_weights, bad_targets)

    def test_iid_rejections_and_exact_cell_multiplicities(self):
        state = _DrawState.from_boundaries((1, 3), quota=False)
        selected = Counter()
        for candidate in range(255):
            cell, following = state.step(candidate)
            selected[cell] += 1
            self.assertIs(following, state)
        self.assertEqual(selected, {0: 85, 1: 170})
        self.assertIsNone(state.step(255))
        for invalid in (None, -1, 256, True):
            with self.subTest(candidate=invalid), self.assertRaises(ValueError):
                state.step(invalid)

    def test_quota_attempts_can_branch_from_the_same_state(self):
        initial = _DrawState.from_boundaries((1, 2, 3), quota=True)
        self.assertIsNone(initial.step(255))
        left, after_left = initial.step(0)
        middle, after_middle = initial.step(1)
        self.assertEqual((left, middle), (0, 1))
        self.assertEqual(after_left.boundaries, (0, 1, 2))
        self.assertEqual(after_middle.boundaries, (1, 1, 2))
        cell, forced = after_middle.step(1)
        self.assertEqual((cell, forced.byte_width), (2, 0))
        self.assertEqual(initial.boundaries, (1, 2, 3))
        with self.assertRaises(ValueError):
            forced.step(0)
        cell, exhausted = forced.step(None)
        self.assertEqual((cell, exhausted.boundaries), (0, (0, 0, 0)))
        with self.assertRaisesRegex(ValueError, "exhausted"):
            exhausted.step(None)

    def test_multibyte_proposal_shrinks_at_the_power_of_256(self):
        # A deck of 256**3 + 1 needs four bytes. After the first
        # accepted draw, the next proposal uses exactly three bytes.
        boundary = 256 ** 3
        state = _DrawState.from_boundaries((boundary, boundary + 1), quota=True)
        self.assertEqual(state.byte_width, 4)
        self.assertIsNone(state.step(2 ** 32 - 1))
        cell, following = state.step(0)
        self.assertEqual((cell, following.byte_width), (0, 3))
        cell, forced = following.step(boundary - 1)
        self.assertEqual((cell, forced.byte_width), (1, 0))
        self.assertEqual(forced.step(None)[0], 0)

    def test_iid_singleton_still_consumes_a_candidate(self):
        iid = _DrawState.from_boundaries((257,), quota=False)
        quota = _DrawState.from_boundaries((257,), quota=True)
        self.assertEqual(iid.byte_width, 2)
        self.assertIsNone(iid.step(65535))
        self.assertEqual(iid.step(15), (0, iid))
        self.assertEqual(quota.byte_width, 0)
        cell, following = quota.step(None)
        self.assertEqual((cell, following.boundaries), (0, (256,)))


if __name__ == "__main__":
    unittest.main()
