"""Independently bound the private-history score of a uniformly shuffled XOR deck.

In a component, applying all listed actions to any supported current card gives
every supported card once. Put the identity action at the current position and
uniformly shuffle the other actions using shared randomness. Each player can
apply their part of each action to their own current label. Together they
reproduce the private input prefixes conditional on the actual current card.
Thus a one-round local strategy can simulate any private-history strategy on a
uniform component. This argument requires no closure of the action list.

To bound one embedded copy, give both players its positions and the full order
of every other card. Its internal order stays uniform. Add the resulting loss
bounds over the disjoint copies. A single best response table for the full
weighted game always attains the lower bound.
"""

import argparse
from fractions import Fraction
from itertools import product
import json
from pathlib import Path


def _fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"{label} must have exactly the fields {', '.join(required)}")


def _matrix(values, label, *, binary=False):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError(f"{label} must be a nonempty matrix")
    if not isinstance(values[0], (list, tuple)) or not values[0]:
        raise ValueError(f"{label} must have at least one column")
    width = len(values[0])
    for row in values:
        if not isinstance(row, (list, tuple)) or len(row) != width:
            raise ValueError(f"{label} must be rectangular")
        if any(type(n) is not int or n < 0 or (binary and n > 1) for n in row):
            raise ValueError(f"invalid entry in {label}")
    return len(values), width


def _permutation(value, size, label):
    if (not isinstance(value, list) or len(value) != size or
            any(type(i) is not int for i in value) or set(value) != set(range(size))):
        raise ValueError(f"{label} must permute the settings 0 through {size - 1}")
    return tuple(value)


def _orbit(component, rows, cols):
    seed = component["seed"]
    if (not isinstance(seed, list) or len(seed) != 2 or any(type(i) is not int for i in seed)
            or not 0 <= seed[0] < rows or not 0 <= seed[1] < cols):
        raise ValueError("seed must be a valid [row, column] pair")
    if not isinstance(component["actions"], list) or not component["actions"]:
        raise ValueError("actions must be a nonempty array")
    actions = []
    for action in component["actions"]:
        _fields(action, ("alice", "bob"), "action")
        actions.append((_permutation(action["alice"], rows, "alice"),
                        _permutation(action["bob"], cols, "bob")))
    identity = (tuple(range(rows)), tuple(range(cols)))
    if actions.count(identity) != 1:
        raise ValueError("actions must include the global identity exactly once")

    def images(x, y):
        return {(a[x], b[y]) for a, b in actions}

    support = images(*seed)
    if len(support) != len(actions) or any(images(*cell) != support for cell in support):
        raise ValueError("actions must enumerate the same support once from every supported cell")
    return sorted(support)


def _local_wins(weights, parity):
    """Exact optimization over local deterministic responses, using integer counts."""
    rows = [i for i, row in enumerate(weights) if any(row)]
    cols = [j for j in range(len(weights[0])) if any(weights[i][j] for i in rows)]
    signed = [[weights[i][j] * (1 - 2 * parity[i][j]) for j in cols] for i in rows]
    if len(rows) > len(cols):
        signed = list(zip(*signed))
    # Enumerate the smaller side, fixing its first sign by global symmetry.
    # For any such assignment, maximizing the other side is independent by column.
    columns = list(zip(*signed))
    best_bias = 0
    for suffix in product((-1, 1), repeat=len(signed) - 1):
        signs = (1, *suffix)
        bias = sum(abs(sum(a * w for a, w in zip(signs, col))) for col in columns)
        best_bias = max(best_bias, bias)
    return (sum(map(sum, weights)) + best_bias) // 2


def verify(weights, target_parity, certificate):
    """Verify an exact cover and return rational bounds as strings. Invalid input raises ValueError."""
    rows, cols = _matrix(weights, "weights")
    if _matrix(target_parity, "target_parity", binary=True) != (rows, cols):
        raise ValueError("target_parity shape must match weights")
    rounds = sum(map(sum, weights))
    if rounds == 0:
        raise ValueError("the deck must contain at least one card")
    _fields(certificate, ("version", "components"), "certificate")
    if type(certificate["version"]) is not int or certificate["version"] != 1:
        raise ValueError("unsupported certificate version")
    if not isinstance(certificate["components"], list) or not certificate["components"]:
        raise ValueError("components must be a nonempty array")

    covered = [[0] * cols for _ in range(rows)]
    reports = []
    for component in certificate["components"]:
        _fields(component, ("name", "copies", "seed", "actions"), "component")
        name, copies = component["name"], component["copies"]
        if not isinstance(name, str) or not name.strip() or type(copies) is not int or copies <= 0:
            raise ValueError("each component needs a nonempty name and positive integer copies")
        support = _orbit(component, rows, cols)
        unit = [[0] * cols for _ in range(rows)]
        for i, j in support:
            covered[i][j] += copies
            if covered[i][j] > weights[i][j]:
                raise ValueError(f"certificate exceeds the deck at ({i}, {j})")
            unit[i][j] = 1
        wins = _local_wins(unit, target_parity)
        loss = len(support) - wins
        reports.append({"name": name, "copies": copies, "support": [list(s) for s in support],
                        "cells_per_copy": len(support), "wins_per_copy": wins,
                        "loss_per_copy": loss, "total_loss": copies * loss})
    if any(covered[i][j] != weights[i][j] for i, j in product(range(rows), range(cols))):
        raise ValueError("certificate must cover the full deck exactly")

    lower = Fraction(_local_wins(weights, target_parity), rounds)
    upper = Fraction(rounds - sum(r["total_loss"] for r in reports), rounds)
    if upper < lower:
        raise ArithmeticError("inconsistent bounds")
    return {"status": "exact" if lower == upper else "interval", "rounds": rounds,
            "lower": str(lower), "upper": str(upper), "components": reports}


def _read_json(path):
    def distinct(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError(f"duplicate JSON field {k!r}")
            result[k] = v
        return result

    def invalid_number(value):
        raise ValueError(f"invalid JSON number {value!r}")

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=distinct,
                      parse_constant=invalid_number)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("certificate", type=Path)
    args = parser.parse_args()
    try:
        game = _read_json(args.result)["winner"]
        report = verify(game["weights"], game["target_parity"], _read_json(args.certificate))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"{parser.prog}: {error}\n")
    print(json.dumps(report, indent=2, allow_nan=False))
