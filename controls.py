"""Compare CHSH subgames and compute a winner's detection-loss thresholds."""

import argparse
from itertools import combinations, product
import json
import math
from pathlib import Path
import sys

from verify_result import physical_probability, verify_result


def detection_terms(settings, scenario):
    pairs = {}
    for i, j in product(range(3), repeat=2):
        a = settings["alice_deg"][i] % 360 + scenario["offset_a_deg"][i] % 360
        b = settings["bob_deg"][j] % 360 + scenario["offset_b_deg"][j] % 360
        ideal = scenario["visibility"] * math.cos(math.radians(a - b))
        pairs[i, j] = (scenario["eta_a"][i], scenario["eta_b"][j], ideal)
    return pairs


def best_chsh(tables):
    best = None
    count = 0
    for aa, bb in product(combinations(range(3), 2), repeat=2):
        cells = list(product(aa, bb))
        for parity in product((0, 1), repeat=4):
            if sum(parity) % 2 != 1:
                continue
            count += 1
            wins = {}
            for name, table in tables.items():
                probabilities = []
                for cell, target in zip(cells, parity):
                    a, b, ideal = table[cell]
                    # Both click, one clicks (unbiased), or neither clicks (+1,+1).
                    both = a * b * (1 + (-1)**target * ideal) / 2
                    one = (a * (1 - b) + (1 - a) * b) / 2
                    neither = (1 - a) * (1 - b) * (target == 0)
                    probabilities.append(both + one + neither)
                wins[name] = math.fsum(probabilities) / 4
            gap = 100 * (min(wins.values()) - 0.75)
            if best is None or gap > best["worst_gap_pp"]:
                best = dict(alice_indices=list(aa), bob_indices=list(bb),
                            target_parity=[list(parity[:2]), list(parity[2:])],
                            classical_win=0.75, scenario_wins=wins, worst_gap_pp=gap)
    return {"games_compared": count, **best}


def margin_coefficients(winner, table):
    weights = winner["weights"]
    total = sum(map(sum, weights))
    constant = [0.5 - winner["classical_win"]]
    linear, quadratic = [], []
    for (i, j), (a, b, ideal) in table.items():
        factor = weights[i][j] * (-1)**winner["target_parity"][i][j] / (2 * total)
        # E_ij(c) = c² a b ideal + (1-ca)(1-cb) for +1 on a missed click.
        constant.append(factor)
        linear.append(-factor * (a + b))
        quadratic.append(factor * a * b * (1 + ideal))
    return math.fsum(constant), math.fsum(linear), math.fsum(quadratic)


def positive_interval_start(constant, linear, quadratic):
    """Left endpoint in [0,1] of the strict-positive component containing 1."""
    tolerance = 16 * sys.float_info.epsilon * max(map(abs, (constant, linear, quadratic)))
    if math.fsum((constant, linear, quadratic)) <= tolerance:
        return None
    roots = []
    if quadratic == 0:
        if linear != 0:
            roots.append(-constant / linear)
    else:
        discriminant = math.fsum((linear * linear, -4 * quadratic * constant))
        d_tol = 16 * sys.float_info.epsilon * (linear * linear + abs(4 * quadratic * constant))
        if discriminant >= -d_tol:
            # Stable even when one root is close to zero.
            q = -0.5 * (linear + math.copysign(math.sqrt(max(discriminant, 0)), linear))
            if q == 0:
                roots.append(0.0)
            else:
                roots.extend((q / quadratic, constant / q))
    return max((r for r in roots if 0 <= r < 1), default=0.0)


def loss_threshold(winner, settings, scenario, table):
    coefs = margin_coefficients(winner, table)
    start = positive_interval_start(*coefs)
    probes = {0, 0.5, 1}
    if start is not None:
        probes.update((start, max(0, start - 1e-6), min(1, start + 1e-6)))
    for scale in probes:
        reduced = {**scenario, **{key: [scale * v for v in scenario[key]]
                                  for key in ("eta_a", "eta_b")}}
        win = physical_probability(winner["weights"], winner["target_parity"],
                                   settings["alice_deg"], settings["bob_deg"], reduced)
        actual = win - winner["classical_win"]
        expected = math.fsum((coefs[0], scale * coefs[1], scale**2 * coefs[2]))
        if abs(actual - expected) > 1e-12:
            raise ValueError("scaled detection model disagrees with its quadratic")
        if scale == start and scale > 0 and abs(actual) > 1e-12:
            raise ValueError("predicted loss threshold does not yield a tie")
    return start


def controls(document):
    verify_result(document)
    settings = document["settings"]
    scenarios = document["scenarios"]
    winner = document["winner"]
    tables = {s["name"]: detection_terms(settings, s) for s in scenarios}
    starts = {s["name"]: loss_threshold(winner, settings, s, tables[s["name"]])
              for s in scenarios}
    return {"best_chsh": best_chsh(tables), "efficiency_scale_thresholds": starts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8-sig"))
    print(json.dumps(controls(result), separators=(",", ":"), allow_nan=False))
