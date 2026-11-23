"""Construct a private-history certificate from the counts and target parity."""

import argparse
from itertools import permutations, product
from pathlib import Path

from ..design.verify import read_result
from ..resources import write_report
from .packing import find_packing
from .verify import verify


def _shift_on_subset(size, subset, offset):
    mapping = list(range(size))
    for i, item in enumerate(subset):
        mapping[item] = subset[(i + offset) % len(subset)]
    return mapping


def component(cells, copies, shape):
    """Build local actions for a rectangle or a six-edge bipartite cycle."""
    cells = tuple(sorted(cells))
    rows, columns = shape
    xs = sorted({x for x, _ in cells})
    ys = sorted({y for _, y in cells})
    if len(cells) == len(xs) * len(ys):
        actions = [
            {"alice": _shift_on_subset(rows, xs, i), "bob": _shift_on_subset(columns, ys, j)}
            for i, j in product(range(len(xs)), range(len(ys)))
        ]
        name = f"{len(xs)}x{len(ys)} rectangle"
    elif shape == (3, 3) and len(cells) == 6:
        missing = sorted(set(product(range(3), repeat=2)) - set(cells))
        if sorted(x for x, _ in missing) != list(range(3)) or len({y for _, y in missing}) != 3:
            return None
        # Relabel Bob so the missing cells form the diagonal. A permutation
        # applied to both labels acts sharply transitively on ordered unequal pairs.
        mate = dict(missing)
        actions = []
        for permutation in permutations(range(3)):
            bob = [0] * 3
            for x in range(3):
                bob[mate[x]] = mate[permutation[x]]
            actions.append({"alice": list(permutation), "bob": bob})
        name = "six-edge cycle"
    else:
        return None
    return {"name": name, "copies": copies, "seed": list(cells[0]), "actions": actions}


def layer_certificate(weights):
    """Take nested supports of positive counts, returning None for an unsupported shape."""
    shape = len(weights), len(weights[0])
    levels = sorted({w for row in weights for w in row if w > 0})
    components = []
    previous = 0
    for level in levels:
        cells = [(x, y) for x, row in enumerate(weights) for y, w in enumerate(row) if w >= level]
        part = component(cells, level - previous, shape)
        if part is None:
            return None
        components.append(part)
        previous = level
    return {"version": 1, "components": components}


def build(weights, parity):
    # This constructor targets the 3x3 research grid; the verifier accepts
    # general rectangular inputs and does not depend on the construction.
    if len(weights) != 3 or any(len(row) != 3 for row in weights):
        raise ValueError("the constructor expects a 3x3 count matrix")
    if any(type(w) is not int or not 1 <= w <= 5 for row in weights for w in row):
        raise ValueError("the constructor expects integer counts from 1 to 5")
    if any(sum(row) != 9 for row in weights) or any(sum(col) != 9 for col in zip(*weights)):
        raise ValueError("the constructor expects balanced row and column sums of nine")
    if len(parity) != 3 or any(len(row) != 3 for row in parity):
        raise ValueError("the constructor expects a 3x3 target parity matrix")
    if any(type(bit) is not int or bit not in (0, 1) for row in parity for bit in row):
        raise ValueError("target parity must contain integer bits")
    layered = layer_certificate(weights)
    if layered is not None:
        layer_report = verify(weights, parity, layered)
        if layer_report["status"] == "exact":
            return layered, layer_report

    supports = find_packing(weights, parity)
    parts = [component(cells, copies, (3, 3)) for cells, copies in supports]
    packed = {"version": 1, "components": parts}
    report = verify(weights, parity, packed)
    # The packing search includes the layered rectangles and six-cycles.
    return packed, report


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, help="write the certificate to this path")
    args = parser.parse_args(argv)
    winner = read_result(args.result)["winner"]
    certificate, _ = build(winner["weights"], winner["target_parity"])
    write_report(certificate, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
