"""Exact tiny-block XOR scores with private histories or delayed public inputs.

A known multiset of question pairs is shuffled uniformly. Each player knows
their own prefix, including the current input. An optional delay determines
when earlier joint questions are revealed. No current remote input, answer,
score, or hidden shuffle is revealed. There is no player communication.
"""

import argparse
import json
from fractions import Fraction
from math import factorial, prod


MAX_ROUNDS = 8
MAX_ORDERS = 12000
MAX_SMALLER_SIDE = 20
MAX_UPDATES_PER_ROUND = 30000000


def _dimensions(table, name):
    if not isinstance(table, (list, tuple)) or not table:
        raise ValueError(f"{name} must be a nonempty rectangular matrix")
    if any(not isinstance(row, (list, tuple)) or not row for row in table):
        raise ValueError(f"{name} must contain nonempty rows")
    width = len(table[0])
    if any(len(row) != width for row in table):
        raise ValueError(f"{name} must be rectangular")
    return len(table), width


def _prefix_games(weights, target_parity):
    if _dimensions(weights, "weights") != _dimensions(target_parity, "target_parity"):
        raise ValueError("weights and target_parity must have equal dimensions")
    cells, remaining = [], []
    for x, row in enumerate(weights):
        for y, count in enumerate(row):
            parity = target_parity[x][y]
            if type(count) is not int or count < 0:
                raise ValueError("weights must be nonnegative integers")
            if type(parity) is not int or parity not in (0, 1):
                raise ValueError("target_parity must contain the integers 0 and 1")
            if count:
                cells.append((x, y, 1 - 2 * parity))
                remaining.append(count)

    length = sum(remaining)
    if not 1 <= length <= MAX_ROUNDS:
        raise ValueError(f"tiny-block enumeration supports 1 to {MAX_ROUNDS} questions")
    orders = factorial(length) // prod(factorial(count) for count in remaining)
    if orders > MAX_ORDERS:
        raise ValueError(f"tiny-block enumeration supports at most {MAX_ORDERS} orders")
    games = [[] for _ in range(length)]

    def visit(alice, bob, left, completions):
        for cell_index, (x, y, sign) in enumerate(cells):
            count = remaining[cell_index]
            if not count:
                continue
            # Every distinct complete ordering is equally likely. This counts
            # the possible suffixes without materializing duplicate leaves.
            suffixes = completions * count // left
            next_a, next_b = alice + (x,), bob + (y,)
            games[length - left].append((next_a, next_b, sign * suffixes))
            if left > 1:
                remaining[cell_index] -= 1
                visit(next_a, next_b, left - 1, suffixes)
                remaining[cell_index] += 1

    visit((), (), length, orders)
    return orders, games


def _best_signed_score(game):
    # Two prefixes together identify the full joint prefix. Each matrix
    # cell is consequently present at most once in this sparse edge list.
    alice = {entry[0] for entry in game}
    bob = {entry[1] for entry in game}
    transpose = len(alice) > len(bob)
    if min(len(alice), len(bob)) > MAX_SMALLER_SIDE:
        raise ValueError(f"one side must have at most {MAX_SMALLER_SIDE} response histories")

    rows = {}
    columns = {}
    for a, b, payoff in game:
        row, col = (b, a) if transpose else (a, b)
        col_index = columns.setdefault(col, len(columns))
        rows.setdefault(row, []).append((col_index, payoff))
    # Fix the most expensive row's sign by the global sign symmetry. In
    # Gray-code order, the cheap rows then also change signs most frequently.
    edges = sorted(rows.values(), key=len)
    flips = len(edges) - 1
    updates = sum(len(edges[i]) * (1 << (flips - i - 1)) for i in range(flips))
    if updates > MAX_UPDATES_PER_ROUND:
        raise ValueError(f"round exceeds {MAX_UPDATES_PER_ROUND} exact score updates")

    columns_sum = [0] * len(columns)
    for row in edges:
        for column, payoff in row:
            columns_sum[column] += payoff
    # For any signs on one side, the optimal signs on the other side
    # take the sign of each column sum independently.
    score = best = sum(abs(value) for value in columns_sum)
    signs = [1] * flips
    for step in range(1, 1 << flips):
        row_index = (step & -step).bit_length() - 1
        signs[row_index] *= -1
        change = 2 * signs[row_index]
        for column, payoff in edges[row_index]:
            old = columns_sum[column]
            new = old + change * payoff
            columns_sum[column] = new
            score += abs(new) - abs(old)
        best = max(best, score)
    return best


def private_position_bounds(weights, target_parity, unrevealed_past=None):
    """Return (per-round optimal win probabilities, mean), all as Fractions.

    Different rounds have disjoint prefix lengths. Their optimal deterministic
    response maps can all be used by the same players because responses do
    not affect later information. Shared randomness cannot improve the mean.
    If unrevealed_past is None, all past remote inputs stay private. If it is
    d >= 0, the most recent d completed rounds stay unannounced and all
    earlier question pairs are public. Each side still knows its own inputs.
    """
    if unrevealed_past is not None and (type(unrevealed_past) is not int or unrevealed_past < 0):
        raise ValueError("unrevealed_past must be None or a nonnegative integer")
    orders, games = _prefix_games(weights, target_parity)
    positions = []
    for past_rounds, game in enumerate(games):
        public_count = 0 if unrevealed_past is None else max(0, past_rounds - unrevealed_past)
        if public_count:
            # Both players know the same public prefix, so response signs
            # may be picked independently for each such information state.
            groups = {}
            for a, b, payoff in game:
                public = (a[:public_count], b[:public_count])
                groups.setdefault(public, []).append((a[public_count:], b[public_count:], payoff))
            signed = sum(_best_signed_score(group) for group in groups.values())
        else:
            signed = _best_signed_score(game)
        positions.append(Fraction(orders + signed, 2 * orders))
    return positions, sum(positions, Fraction()) / len(positions)


def demo(include_rectangular=False):
    examples = {"chsh": ([[1, 1], [1, 1]], [[0, 0], [0, 1]])}
    if include_rectangular:
        examples["two_by_three"] = ([[1, 1, 1], [1, 1, 1]], [[0, 0, 0], [0, 1, 1]])
    result = {}
    for name, (weights, parity) in examples.items():
        positions, mean = private_position_bounds(weights, parity)
        result[name] = {"weights": weights, "target_parity": parity,
                        "private_by_round": list(map(str, positions)),
                        "private_mean": str(mean), "iid_local": str(positions[0])}
        if name == "chsh":
            by_delay = {}
            for delay in range(len(positions)):
                delayed, block_mean = private_position_bounds(weights, parity, delay)
                by_delay[str(delay)] = {"by_round": list(map(str, delayed)), "mean": str(block_mean)}
            result[name]["by_unrevealed_past_rounds"] = by_delay
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rectangular", action="store_true", help="also run the full 2-by-3 example")
    args = parser.parse_args()
    print(json.dumps(demo(args.rectangular), indent=2))
