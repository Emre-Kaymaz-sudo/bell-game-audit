"""Exact expected local scores under IID questions and shuffled public quotas.

One quota block contains exactly n[x,y] copies of each question pair in a
uniformly random order. Both parties learn all earlier joint questions before
the next round. Each sees only their own current question. Earlier answers
carry no further information about the independent referee's unseen order.
Answers never affect later questions, so optimizing each public state is
jointly achievable by agreeing on its response tables before the block.
"""

import argparse
from fractions import Fraction
from functools import lru_cache
from itertools import combinations, product
from math import comb, prod
from pathlib import Path

import numpy as np

from ..certificates.build import build
from ..design.verify import read_result, verify_result
from ..resources import write_report


def position_bounds(weights, target_parity):
    """Return the IID local value and quota values in play order, as Fractions."""
    counts = np.asarray(weights)
    parity = np.asarray(target_parity)
    if counts.ndim != 2 or 0 in counts.shape or counts.dtype.kind not in "iu":
        raise ValueError("weights must be a nonempty rectangular integer matrix")
    if np.any(counts < 0):
        raise ValueError("quotas must be nonnegative")
    if parity.shape != counts.shape or parity.dtype.kind not in "iu" or np.any((parity != 0) & (parity != 1)):
        raise ValueError("target parity must match weights and contain only 0 or 1")
    quotas = list(map(int, counts.ravel()))
    rounds = sum(quotas)
    rows, columns = counts.shape
    state_count = prod(n + 1 for n in quotas)
    if not 1 <= rounds <= 56 or rows + columns > 10 or state_count > 1_000_000:
        raise ValueError("exact audit supports 1–56 rounds, up to 10 local settings in total, and 1 million states")
    # At a fixed k, all multiplicities sum to C(N,k), and a state wins at most k.
    # This bound covers products and the complete accumulation into each int64 bin.
    if rounds * comb(rounds, rounds // 2) > np.iinfo(np.int64).max:
        raise ValueError("integer tally would exceed int64 capacity")

    # Flipping every response on both sides preserves every XOR. Fix Alice's
    # first bit to zero and score each distinct deterministic table once.
    responses = np.array([(0, *bits) for bits in product((0, 1), repeat=rows + columns - 1)])
    alice, bob = responses[:, :rows, None], responses[:, None, rows:]
    wins = (alice ^ bob) == parity
    wins_by_strategy = wins.reshape(len(responses), -1).T.astype(np.int64)
    ways = [np.array([comb(n, r) for r in range(n + 1)], dtype=np.int64) for n in quotas]
    shapes = tuple(n + 1 for n in quotas)
    mass = np.zeros(rounds + 1, dtype=np.int64)
    win_mass = np.zeros_like(mass)
    for start in range(0, state_count, 4096):
        ids = np.arange(start, min(start + 4096, state_count), dtype=np.int64)
        remaining = np.stack(np.unravel_index(ids, shapes), axis=1).astype(np.int64, copy=False)
        k = remaining.sum(axis=1)
        # Each remaining multiset represents product_i C(n_i,r_i) labelled subsets.
        multiplicity = np.ones(len(ids), dtype=np.int64)
        for cell, binomials in enumerate(ways):
            multiplicity *= binomials[remaining[:, cell]]
        best = (remaining @ wins_by_strategy).max(axis=1)
        np.add.at(mass, k, multiplicity)
        np.add.at(win_mass, k, multiplicity * best)

    by_position = []
    for k in range(rounds, 0, -1):
        denominator = comb(rounds, k)
        if int(mass[k]) != denominator:
            raise ArithmeticError(f"hypergeometric mass did not normalize at {k} remaining")
        by_position.append(Fraction(int(win_mass[k]), k * denominator))
    # Before the first draw, the remaining deck gives exactly the IID weights.
    return by_position[0], by_position


def ratio(value):
    return {"fraction": str(value), "value": float(value)}


def _private_rectangle_certificate(weights, parity):
    """Pack disjoint four-card CHSH subdecks; each forces one expected loss.

    Used on the validated 3x3 input of audit(). The independent order of each
    subdeck is uniform even if its positions and every other card are disclosed.
    See the local simulation proof in PRIOR_ART.md.
    """
    rows, cols = len(weights), len(weights[0])
    cells = tuple(int(w) for row in weights for w in row)
    rectangles = []
    for a, b in product(combinations(range(rows), 2), combinations(range(cols), 2)):
        rectangle = tuple(product(a, b))
        if sum(parity[x][y] for x, y in rectangle) % 2:
            rectangles.append(tuple(x * cols + y for x, y in rectangle))

    @lru_cache(maxsize=None)
    def pack(remaining):
        best = ()
        for rect in rectangles:
            if all(remaining[i] for i in rect):
                after = list(remaining)
                for i in rect:
                    after[i] -= 1
                candidate = (rect,) + pack(tuple(after))
                if len(candidate) > len(best):
                    best = candidate
        return best

    packing = pack(cells)
    upper = Fraction(sum(cells) - len(packing), sum(cells))
    return upper, [[list(divmod(i, cols)) for i in rect] for rect in packing]


def audit(document):
    verify_result(document)
    winner = document["winner"]
    iid, positions = position_bounds(winner["weights"], winner["target_parity"])
    rounds = len(positions)
    expected_wins = sum(positions, Fraction())
    quota = expected_wins / rounds
    rectangle_upper, rectangles = _private_rectangle_certificate(winner["weights"], winner["target_parity"])
    _, private = build(winner["weights"], winner["target_parity"])
    private_upper = min(rectangle_upper, Fraction(private["upper"]))
    physical = {
        name: {"fixed_expected_win": p, "gap_vs_iid_pp": 100 * (p - float(iid)),
               "gap_vs_private_quota_interval_pp": [100 * (p - float(private_upper)),
                                                    100 * (p - float(iid))],
               "gap_vs_public_quota_pp": 100 * (p - float(quota))}
        for name, p in winner["scenario_wins"].items()
    }
    return {
        "rounds": rounds,
        "iid_classical_win": ratio(iid),
        "private_quota_classical_interval": {
            "lower": ratio(iid),
            "upper": ratio(private_upper),
            "status": "exact" if iid == private_upper else "interval",
            "component_bound": private,
            "rectangle_only_upper": ratio(rectangle_upper),
            "disjoint_chsh_rectangles": rectangles,
        },
        "public_quota_classical_win": ratio(quota),
        "public_quota_expected_block_wins": ratio(expected_wins),
        "classical_increase_pp": ratio(100 * (quota - iid)),
        "public_quota_by_position": [
            {"round": i + 1, "remaining": rounds - i, **ratio(value)}
            for i, value in enumerate(positions)
        ],
        "fixed_physical_scenarios": physical,
    }


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, help="write the audit to a UTF-8 JSON file")
    args = parser.parse_args(argv)
    try:
        output = audit(read_result(args.result))
    except (OSError, ValueError, ArithmeticError, KeyError, TypeError) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")
    write_report(output, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
