"""Check the private-history certificates on the entire original 27-card grid."""

import argparse
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

import numpy as np

from .build import build
from ..design.search import balanced_weights
from ..resources import write_report


def survey(tables=None):
    # Row and column flips of the target are local changes of output labels.
    # A representative has a zero first row and column. Any support certificate
    # for it can be scored against all 32 original targets in that class.
    targets = np.array(list(product((0, 1), repeat=9)), dtype=int).reshape(512, 3, 3)
    groups = defaultdict(list)
    for i, target in enumerate(targets):
        canonical = target ^ target[:1, :] ^ target[:, :1] ^ target[0, 0]
        groups[tuple(canonical.ravel())].append(i)
    representatives = [(np.asarray(key).reshape(3, 3).tolist(), np.asarray(indices))
                       for key, indices in groups.items()]

    answers = np.array(list(product((0, 1), repeat=3)), dtype=int)
    local_tables = (answers[:, None, :, None] ^ answers[None, :, None, :]).reshape(64, 3, 3)
    errors = (local_tables[None, :, :, :] != targets[:, None, :, :]).astype(int)
    errors = errors.reshape(512, 64, 9)
    support_losses = {}
    histogram = Counter()
    unresolved_example = None
    n_tables = 0
    weight_tables = balanced_weights() if tables is None else tables
    for weights in weight_tables:
        n_tables += 1
        weights = np.array(weights, dtype=int)
        weight_rows = weights.tolist()
        full_loss = (errors @ weights.ravel()).min(axis=1)
        for canonical, indices in representatives:
            _, checked = build(weight_rows, canonical)
            forced = np.zeros(len(indices), dtype=int)
            for part in checked["components"]:
                cells = tuple(3 * x + y for x, y in part["support"])
                if cells not in support_losses:
                    support_losses[cells] = errors[:, :, list(cells)].sum(axis=2).min(axis=1)
                forced += part["copies"] * support_losses[cells][indices]
            differences = full_loss[indices] - forced
            if np.any(differences < 0):
                raise ArithmeticError("certificate contradicts a feasible static response")
            histogram.update(map(int, differences))
            if unresolved_example is None and np.any(differences):
                first = int(np.flatnonzero(differences)[0])
                unresolved_example = {
                    "weights": weight_rows,
                    "target_parity": targets[indices[first]].tolist(),
                    "bound_gap_in_wins": int(differences[first]),
                }
    return {
        "weight_tables": n_tables,
        "targets_per_table": len(targets),
        "representatives_per_table": len(groups),
        "verified_component_certificates": n_tables * len(groups),
        "local_responses_scored_per_target": len(local_tables),
        "labelled_games": sum(histogram.values()),
        "exact_private_values": histogram[0],
        "bound_gap_in_wins_histogram": {str(k): v for k, v in sorted(histogram.items())},
        "first_unresolved_example": unresolved_example,
    }


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--output", type=Path, help="write a UTF-8 summary for the full grid")
    args = parser.parse_args(argv)
    write_report(survey(), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
