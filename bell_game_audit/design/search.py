"""Inverse design of a three-setting XOR game on a finite, balanced input grid."""

import argparse
from copy import deepcopy
from itertools import product
import json
from pathlib import Path

import numpy as np

from ..resources import default_model
from .solver import planar_witness, quantum_upper


def game_signs():
    return np.asarray(list(product((-1, 1), repeat=9)), dtype=int)


def local_responses():
    # Simultaneously flipping both players' outputs leaves their product unchanged.
    alice = [(1,) + suffix for suffix in product((-1, 1), repeat=2)]
    bob = list(product((-1, 1), repeat=3))
    return np.array([np.outer(a, b).ravel() for a in alice for b in bob])


def balanced_weights():
    rows = [r for r in product(range(1, 6), repeat=3) if sum(r) == 9]
    row_set = set(rows)
    for first, second in product(rows, repeat=2):
        third = tuple(9 - a - b for a, b in zip(first, second))
        if third in row_set:
            yield np.array([first, second, third], dtype=int)


def model_correlations(model):
    angles = model["settings"]
    scenarios = model["scenarios"]
    if not scenarios or len({s["name"] for s in scenarios}) != len(scenarios):
        raise ValueError("specify at least one scenario and give each a unique name")

    def vector(values, field):
        array = np.asarray(values, dtype=float)
        if array.shape != (3,) or not np.isfinite(array).all():
            raise ValueError(f"{field} requires three finite numbers")
        return array

    alice = vector(angles["alice_deg"], "alice_deg")
    bob = vector(angles["bob_deg"], "bob_deg")
    correlations = []
    for s in scenarios:
        a = np.deg2rad(alice + vector(s["offset_a_deg"], "offset_a_deg"))
        b = np.deg2rad(bob + vector(s["offset_b_deg"], "offset_b_deg"))
        efficiency_a = vector(s["eta_a"], "eta_a")[:, None]
        efficiency_b = vector(s["eta_b"], "eta_b")[None, :]
        visibility = float(s["visibility"])
        if not 0 <= visibility <= 1 or any(
            np.any((e < 0) | (e > 1)) for e in (efficiency_a, efficiency_b)
        ):
            raise ValueError("visibility and detection efficiencies must be in [0,1]")
        coincidence = efficiency_a * efficiency_b
        neither = (1 - efficiency_a) * (1 - efficiency_b)
        correlations.append(coincidence * visibility * np.cos(a[:, None] - b) + neither)
    return np.array(correlations).reshape(-1, 9)


def record(weights, sign, local_bias, physical_biases, names):
    denominator = weights.sum()
    classical = (1 + local_bias / denominator) / 2
    wins = (1 + physical_biases / denominator) / 2
    return {
        "weights": weights.tolist(),
        "target_parity": ((1 - sign.reshape(3, 3)) // 2).tolist(),
        "classical_win": float(classical),
        "scenario_wins": dict(zip(names, map(float, wins))),
        "worst_gap_pp": float(100 * (wins.min() - classical)),
    }


def search_tables(model):
    """Score all tables on this calibration, retaining the first winner on ties."""
    correlations = model_correlations(model)
    names = [s["name"] for s in model["scenarios"]]
    signs = game_signs()
    classical_responses = local_responses()
    best_gap = best_reference_gap = -np.inf
    winner = uniform = reference = None
    count = 0
    for weights in balanced_weights():
        matrices = signs * weights.ravel()
        local = (matrices @ classical_responses.T).max(axis=1)
        physical = matrices @ correlations.T
        gaps = physical.min(axis=1) - local
        index = int(np.argmax(gaps))
        count += 1
        if gaps[index] > best_gap + 1e-12:
            best_gap = float(gaps[index])
            winner = record(weights, signs[index], local[index], physical[index], names)
        if np.all(weights == 3):
            uniform = record(weights, signs[index], local[index], physical[index], names)
        reference_gaps = physical[:, 0] - local
        first = int(np.argmax(reference_gaps))
        if reference_gaps[first] > best_reference_gap + 1e-12:
            best_reference_gap = float(reference_gaps[first])
            reference = record(weights, signs[first], local[first], physical[first], names)

    return {
        "settings": deepcopy(model["settings"]),
        "scenarios": deepcopy(model["scenarios"]),
        "weight_tables": count,
        "parity_tables": len(signs),
        "labelled_candidates": count * len(signs),
        "winner": winner,
        "best_uniform": uniform,
        "optimized_for_first_scenario": reference,
    }


def search_model(model):
    """Compute the full design report from an in-memory calibration."""
    result = search_tables(model)
    winner = result["winner"]
    weights = np.array(winner["weights"])
    signed = weights / weights.sum() * (1 - 2 * np.array(winner["target_parity"]))
    alice, bob = planar_witness(signed, restarts=32, seed=2026)
    unconstrained_bias = np.sum(signed * (alice @ bob.T))
    ideal_interval = [
        float((1 + unconstrained_bias) / 2), float((1 + quantum_upper(signed, alice, bob)) / 2)
    ]
    return {**result, "winner": {**winner, "ideal_reoptimized_win_interval": ideal_interval}}


def search(model_path):
    """Read a calibration from a JSON path and compute its design report."""
    return search_model(json.loads(Path(model_path).read_text(encoding="utf-8")))


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--model", type=Path, default=default_model)
    parser.add_argument("--output", type=Path, help="write the result to this JSON file")
    args = parser.parse_args(argv)
    result = json.dumps(search(args.model), indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
