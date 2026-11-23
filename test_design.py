"""Independent checks for two-player XOR game bias calculations."""

import itertools
import math
import unittest

import numpy as np

from solver import classical_bias, planar_witness, quantum_upper


def exhaustive_classical_bias(matrix):
    """Independent oracle for small games, enumerating both players' answers."""
    n_rows, n_cols = matrix.shape
    return max(
        sum(matrix[i, j] * a[i] * b[j] for i in range(n_rows) for j in range(n_cols))
        for a in itertools.product((-1, 1), repeat=n_rows)
        for b in itertools.product((-1, 1), repeat=n_cols)
    )


def unit_vectors(angles):
    return np.array([(math.cos(theta), math.sin(theta)) for theta in angles])


class XorGameBoundsTests(unittest.TestCase):
    def witness_score(self, matrix, alice, bob):
        alice = np.asarray(alice)
        bob = np.asarray(bob)
        self.assertEqual(alice.shape, (matrix.shape[0], 2))
        self.assertEqual(bob.shape, (matrix.shape[1], 2))
        for vector in itertools.chain(alice, bob):
            self.assertAlmostEqual(math.hypot(*vector), 1.0, places=8)
        return sum(
            matrix[i, j] * sum(x * y for x, y in zip(a, b))
            for i, a in enumerate(alice)
            for j, b in enumerate(bob)
        )

    def test_chsh(self):
        matrix = np.array([[1.0, 1.0], [1.0, -1.0]]) / 4
        self.assertAlmostEqual(classical_bias(matrix), 0.5)
        alice, bob = planar_witness(matrix, restarts=8, seed=14)
        attained = self.witness_score(matrix, alice, bob)
        optimum = math.sqrt(0.5)
        self.assertAlmostEqual(attained, optimum, places=6)
        upper = quantum_upper(matrix, alice, bob)
        self.assertGreaterEqual(upper, optimum - 1e-10)
        self.assertAlmostEqual(upper, optimum, places=6)

    def test_three_setting_chain(self):
        matrix = np.array([[1.0, 0.0, -1.0], [1.0, 1.0, 0.0], [0.0, 1.0, 1.0]]) / 6
        # Successive measurements on the cycle differ by pi / 6. The
        # negative edge closes the cycle with precisely the opposite sign.
        alice = unit_vectors([0.0, math.pi / 3, 2 * math.pi / 3])
        bob = unit_vectors([math.pi / 6, math.pi / 2, 5 * math.pi / 6])
        optimum = math.cos(math.pi / 6)
        self.assertAlmostEqual(classical_bias(matrix), 2 / 3)
        self.assertAlmostEqual(self.witness_score(matrix, alice, bob), optimum)
        upper = quantum_upper(matrix, alice, bob)
        self.assertGreaterEqual(upper, optimum - 1e-10)
        self.assertAlmostEqual(upper, optimum, places=6)

        # A certificate must also be valid when the supplied witness is poor.
        aligned = unit_vectors([0.0] * 3)
        self.assertGreaterEqual(quantum_upper(matrix, aligned, aligned), optimum - 1e-10)

    def test_three_dimensional_strategy_exceeds_planar_score(self):
        # For orthogonal Bob axes in R^3, Alice aligns her four axes with
        # these signed triples. Each row then contributes sqrt(3) / 12.
        matrix = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]) / 12
        spatial_score = 1 / math.sqrt(3)
        self.assertAlmostEqual(classical_bias(matrix), 0.5)
        alice, bob = planar_witness(matrix, restarts=8, seed=4)
        self.assertLess(self.witness_score(matrix, alice, bob), spatial_score - 1e-5)
        self.assertGreaterEqual(quantum_upper(matrix, alice, bob), spatial_score - 1e-10)

    def test_rank_one_and_scales(self):
        # A deterministic strategy can satisfy each nonzero coefficient
        # simultaneously in a signed outer product.
        base = np.outer([1.0, -2.0], [-3.0, 1.0, 2.0]) / 18
        for factor in (1.0, 0.25, -2.0):
            with self.subTest(factor=factor):
                matrix = factor * base
                optimum = abs(factor)
                self.assertAlmostEqual(classical_bias(matrix), optimum)
                alice, bob = planar_witness(matrix, restarts=5, seed=17)
                self.assertAlmostEqual(self.witness_score(matrix, alice, bob), optimum)
                self.assertGreaterEqual(quantum_upper(matrix, alice, bob), optimum - 1e-10)

    def test_rectangular_game_with_empty_settings(self):
        # Nonuniform input weights, one unused question for each player.
        matrix = np.array([[0, 2, -3, 1], [0, 0, 0, 0], [0, 1, 2, 1]], dtype=float) / 10
        for game in (matrix, matrix.T):
            with self.subTest(shape=game.shape):
                expected = exhaustive_classical_bias(game)
                self.assertAlmostEqual(classical_bias(game), expected)
                alice, bob = planar_witness(game, restarts=8, seed=22)
                attained = self.witness_score(game, alice, bob)
                self.assertGreaterEqual(attained, expected - 1e-8)
                self.assertLessEqual(attained, 1 + 1e-10)
                upper = quantum_upper(game, alice, bob)
                self.assertTrue(math.isfinite(upper))
                self.assertGreaterEqual(upper, attained - 1e-10)


if __name__ == "__main__":
    unittest.main()
