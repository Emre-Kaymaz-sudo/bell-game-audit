"""Exact counting tests of the referee's finite random-input mapping."""

import io
import unittest
from collections import Counter
from itertools import product

from bell_game_audit.protocol.referee import replay


WEIGHTS = [[1, 2, 3], [4, 5, 6], [1, 2, 3]]
PARITY = [[0, 1, 0], [1, 0, 1], [0, 1, 0]]


class RefereeTests(unittest.TestCase):
    def test_known_bytes(self):
        tape = bytes([243, 255, 0, 2, 3, 27, 242])
        log = replay(WEIGHTS, PARITY, io.BytesIO(tape), 5)
        self.assertEqual(log["source_bytes_consumed"], 7)
        self.assertEqual(log["source_bytes_rejected"], 2)
        self.assertEqual(
            [(r["x"], r["y"], r["target_parity"]) for r in log["referee_rounds"]],
            [(0, 0, 0), (0, 1, 1), (0, 2, 0), (0, 0, 0), (2, 2, 0)],
        )
        self.assertEqual(log, replay(WEIGHTS, PARITY, io.BytesIO(tape), 5))

    def test_all_possible_bytes(self):
        # Force all rejected bytes to be read before presenting every valid
        # byte once. Each unit of game weight must have nine preimages.
        tape = bytes(range(243, 256)) + bytes(range(243))
        log = replay(WEIGHTS, PARITY, io.BytesIO(tape), 243)
        self.assertEqual(log["source_bytes_consumed"], 256)
        self.assertEqual(log["source_bytes_rejected"], 13)
        self.assertEqual(log["question_counts"], [[9 * w for w in row] for row in WEIGHTS])

    def test_exhaustion_never_substitutes_a_question(self):
        with self.assertRaisesRegex(ValueError, "after 1 of 2 rounds"):
            replay(WEIGHTS, PARITY, io.BytesIO(bytes([2, 255])), 2)

    def test_general_integer_weights(self):
        # A total weight of 257 needs two-byte proposals. 65535 is the
        # only rejection and 256 selects the second question.
        log = replay([[256, 1]], [[0, 1]], io.BytesIO(bytes.fromhex("ffff0100")), 1)
        self.assertEqual(log["source_bytes_rejected"], 2)
        self.assertEqual(log["source_bytes_consumed"], 4)
        self.assertEqual(log["question_counts"], [[0, 1]])

    def test_quota_uniform_over_four_question_permutations(self):
        # Independent uniform ranks for 4, 3 and 2 remaining slots give 24 paths.
        orders = Counter()
        for ranks in product(range(4), range(3), range(2)):
            log = replay([[1, 1], [1, 1]], [[0, 0], [0, 1]], io.BytesIO(bytes(ranks)),
                         None, schedule="quota")
            order = tuple((r["x"], r["y"]) for r in log["referee_rounds"])
            self.assertEqual(log["question_counts"], [[1, 1], [1, 1]])
            self.assertEqual(log["source_bytes_consumed"], 3)
            self.assertEqual(log["quota_block_length"], 4)
            self.assertTrue(log["quota_block_complete"])
            self.assertEqual(log["schedule"], "quota")
            orders[order] += 1
        self.assertEqual(len(orders), 24)
        self.assertEqual(set(orders.values()), {1})

    def test_quota_repeated_cells_and_forced_suffix(self):
        orders = Counter()
        for first, second in product(range(3), range(2)):
            tape = io.BytesIO(bytes([255, first, second]))  # first byte rejected for total 3
            log = replay([[1, 2]], [[1, 0]], tape, 3, schedule="quota")
            order = tuple(r["y"] for r in log["referee_rounds"])
            self.assertEqual(log["source_bytes_rejected"], 1)
            self.assertEqual(log["source_bytes_consumed"], 2 if first == 0 else 3)
            self.assertEqual(log["question_counts"], [[1, 2]])
            orders[order] += 1
        self.assertEqual(orders, {(0, 1, 1): 2, (1, 0, 1): 2, (1, 1, 0): 2})
        forced = replay([[4]], [[1]], io.BytesIO(), None, schedule="quota")
        self.assertEqual(forced["question_counts"], [[4]])
        self.assertEqual(forced["source_bytes_consumed"], 0)

    def test_quota_prefix_and_exhaustion(self):
        tape = bytes([1, 0, 0])
        full = replay([[1, 1, 1]], [[0, 1, 0]], io.BytesIO(tape), None, schedule="quota")
        for length in range(3):
            prefix = replay([[1, 1, 1]], [[0, 1, 0]], io.BytesIO(tape), length, schedule="quota")
            self.assertEqual(prefix["referee_rounds"], full["referee_rounds"][:length])
            self.assertFalse(prefix["quota_block_complete"])
        with self.assertRaisesRegex(ValueError, "after 1 of 3 rounds"):
            replay([[1, 1, 1]], [[0, 1, 0]], io.BytesIO(bytes([0])), None, schedule="quota")
        with self.assertRaisesRegex(ValueError, "cannot exceed one block"):
            replay([[1]], [[0]], io.BytesIO(), 2, schedule="quota")

    def test_quota_multibyte_proposals(self):
        tape = io.BytesIO(bytes.fromhex("ffff0100"))
        log = replay([[256, 1]], [[0, 1]], tape, None, schedule="quota")
        self.assertEqual(log["source_bytes_rejected"], 2)
        self.assertEqual(log["source_bytes_consumed"], 4)
        self.assertEqual(log["question_counts"], [[256, 1]])


if __name__ == "__main__":
    unittest.main()
