"""Inverse design of a three-setting XOR game on a finite, balanced input grid."""

import argparse
from copy import deepcopy
from itertools import product
from pathlib import Path

import numpy as np

from ..resources import default_model, read_model, write_report
from .solver import planar_witness, quantum_upper
from .verify import number, object_value, vector


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


def _angle_vector(settings, key):
    # Reduce before adding the offset, keeping ordinary laboratory angles and
    # their published floating-point scores unchanged.
    return np.array([value % 360 if abs(value) > 360 else value
                     for value in vector(settings, key)], dtype=float)


def model_correlations(model):
    """Return one row of nine correlations per validated calibration scenario."""
    object_value(model, "model")
    angles = object_value(model["settings"], "settings")
    scenarios = model["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a nonempty array")
    alice = _angle_vector(angles, "alice_deg")
    bob = _angle_vector(angles, "bob_deg")
    names = set()
    correlations = []
    for index, item in enumerate(scenarios):
        scenario = object_value(item, f"scenarios[{index}]")
        name = scenario["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError(f"scenarios[{index}].name must be a nonempty unique string")
        names.add(name)
        a = np.deg2rad(alice + _angle_vector(scenario, "offset_a_deg"))
        b = np.deg2rad(bob + _angle_vector(scenario, "offset_b_deg"))
        efficiency_a = np.array(vector(scenario, "eta_a", 0, 1), dtype=float)[:, None]
        efficiency_b = np.array(vector(scenario, "eta_b", 0, 1), dtype=float)[None, :]
        visibility = number(scenario["visibility"], "visibility", 0, 1)
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


def _rank_tables(correlations, names):
    """Rank the balanced tables against precomputed scenario correlations."""
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
        "weight_tables": count,
        "parity_tables": len(signs),
        "labelled_candidates": count * len(signs),
        "winner": winner,
        "best_uniform": uniform,
        "optimized_for_first_scenario": reference,
    }


def search_tables(model):
    """Score all tables on this calibration, retaining the first winner on ties."""
    correlations = model_correlations(model)
    ranking = _rank_tables(correlations, [scenario["name"] for scenario in model["scenarios"]])
    return {"settings": deepcopy(model["settings"]), "scenarios": deepcopy(model["scenarios"]),
            **ranking}


def _payoff_matrix(game):
    weights = np.array(game["weights"])
    signs = 1 - 2 * np.array(game["target_parity"])
    return weights / weights.sum() * signs


def search_model(model):
    """Compute the full design report from an in-memory calibration."""
    result = search_tables(model)
    winner = result["winner"]
    signed = _payoff_matrix(winner)
    alice, bob = planar_witness(signed, restarts=32, seed=2026)
    unconstrained_bias = np.sum(signed * (alice @ bob.T))
    ideal_interval = [
        float((1 + unconstrained_bias) / 2), float((1 + quantum_upper(signed, alice, bob)) / 2)
    ]
    return {**result, "winner": {**winner, "ideal_reoptimized_win_interval": ideal_interval}}


def search(model_path):
    """Read a calibration from a JSON path and compute its design report."""
    return search_model(read_model(model_path))


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--model", type=Path, default=default_model)
    parser.add_argument("--output", type=Path, help="write the result to this JSON file")
    args = parser.parse_args(argv)
    write_report(search(args.model), args.output)


if __name__ == "__main__":
    main()
