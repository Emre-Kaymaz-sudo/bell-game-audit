"""Independently verify the reported 3-by-3 XOR game witness, using only Python."""

import argparse
import json
import math
import sys
from itertools import product
from pathlib import Path


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def reject_constant(token):
    raise ValueError(f"invalid JSON numeric literal {token!r}")


def read_result(path: Path):
    """Read a saved design, rejecting duplicate keys and non-finite literals."""
    with path.open(encoding="utf-8-sig") as source:
        document = json.load(source, object_pairs_hook=unique_keys, parse_constant=reject_constant)
    return object_value(document, "result")


def object_value(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def triple(value, label):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must be an array of length 3")
    return value


def number(value, label, lower=-math.inf, upper=math.inf):
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise ValueError(f"{label} must be a finite number")
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be in [{lower}, {upper}]")
    return value


def vector(obj, key, lower=-math.inf, upper=math.inf):
    return [number(value, f"{key}[{i}]", lower, upper)
            for i, value in enumerate(triple(obj[key], key))]


def integer_matrix(obj, key, lower, upper):
    matrix = triple(obj[key], key)
    for i, row in enumerate(matrix):
        for j, value in enumerate(triple(row, f"{key}[{i}]")):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{key}[{i}][{j}] must be an integer in [{lower}, {upper}]")
    return matrix


def classical_probability(weights, parity):
    best = 0
    for answers in product((0, 1), repeat=6):
        score = sum(weights[i][j] for i in range(3) for j in range(3)
                    if (answers[i] ^ answers[j + 3]) == parity[i][j])
        best = max(best, score)
    return best / 27


def physical_probability(weights, parity, alice, bob, scenario):
    visibility = number(scenario["visibility"], "visibility", 0, 1)
    eta_a = vector(scenario, "eta_a", 0, 1)
    eta_b = vector(scenario, "eta_b", 0, 1)
    offset_a = vector(scenario, "offset_a_deg")
    offset_b = vector(scenario, "offset_b_deg")
    angles_a = [(angle % 360 + offset % 360) % 360 for angle, offset in zip(alice, offset_a)]
    angles_b = [(angle % 360 + offset % 360) % 360 for angle, offset in zip(bob, offset_b)]
    terms = []
    for i, j in product(range(3), repeat=2):
        angle = math.radians(angles_a[i] - angles_b[j])
        both_detected = eta_a[i] * eta_b[j]
        both_missed = (1 - eta_a[i]) * (1 - eta_b[j])
        correlation = both_detected * visibility * math.cos(angle) + both_missed
        win = (1 + (-1) ** parity[i][j] * correlation) / 2
        terms.append(weights[i][j] * win)
    return math.fsum(terms) / 27


def compare(label, reported, computed, lower, upper, tolerance):
    number(reported, label, lower, upper)
    if abs(reported - computed) > tolerance:
        raise ValueError(f"{label} reports {reported!r}, recomputed {computed:.15g}")


def verify_result(document):
    root = object_value(document, "result")
    settings = object_value(root["settings"], "settings")
    alice, bob = vector(settings, "alice_deg"), vector(settings, "bob_deg")
    winner = object_value(root["winner"], "winner")
    weights = integer_matrix(winner, "weights", 1, 5)
    if any(sum(line) != 9 for line in [*weights, *zip(*weights)]):
        raise ValueError("each row and column of weights must sum to 9")
    parity = integer_matrix(winner, "target_parity", 0, 1)
    classical = classical_probability(weights, parity)
    compare("classical_win", winner["classical_win"], classical, 0, 1, 1e-9)

    scenarios = root["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a nonempty array")
    wins = object_value(winner["scenario_wins"], "scenario_wins")
    actual = {}
    for index, item in enumerate(scenarios):
        scenario = object_value(item, f"scenarios[{index}]")
        name = scenario["name"]
        if not isinstance(name, str) or not name.strip() or name in actual:
            raise ValueError(f"scenarios[{index}].name must be a nonempty unique string")
        actual[name] = physical_probability(weights, parity, alice, bob, scenario)
    if actual.keys() != wins.keys():
        raise ValueError("scenario_wins must have exactly one entry per scenario name")
    for name, win in actual.items():
        compare(f"scenario_wins[{name!r}]", wins[name], win, 0, 1, 1e-9)
    gap = 100 * (min(actual.values()) - classical)
    compare("worst_gap_pp", winner["worst_gap_pp"], gap, -100, 100, 1e-8)
    return classical, gap, len(actual)


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args(argv)
    try:
        classical, gap, count = verify_result(read_result(args.result))
    except (OSError, ValueError, KeyError, OverflowError) as exc:
        print(f"Witness verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"Witness verified: classical win {classical:.12f} over 64 strategies, "
          f"worst gap {gap:+.9f} percentage points across {count} scenarios.")
    print("Scope: reported witness arithmetic. Exhaustive search optimality is a separate claim.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
