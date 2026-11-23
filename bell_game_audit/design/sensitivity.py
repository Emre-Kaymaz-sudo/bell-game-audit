"""Compare a frozen game with a redesigned game as one measurement drifts."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from ..resources import default_model
from .search import model_correlations, search_tables


def _shift_middle_setting(scenario, offset):
    first, middle, last = scenario["offset_b_deg"]
    return deepcopy({
        **scenario,
        "name": f"{scenario['name']}_offset_{offset:+d}",
        "offset_b_deg": [first, middle + offset, last],
    })


def with_extra_offsets(model, degrees):
    """Include both signed endpoints and zero drift on Bob's middle setting.

    Each source scenario keeps its place and gets one variant per distinct
    offset, in ascending order. Each variant owns its calibration data.
    """
    offsets = sorted({-degrees, 0, degrees})
    scenarios = [_shift_middle_setting(scenario, offset)
                 for scenario in model["scenarios"] for offset in offsets]
    return {key: scenarios if key == "scenarios" else deepcopy(value)
            for key, value in model.items()}


def sweep(model):
    frozen = search_tables(model)["winner"]
    weights = np.array(frozen["weights"])
    signed = weights * (1 - 2 * np.array(frozen["target_parity"])) / weights.sum()
    rows = []
    for degrees in range(0, 46, 5):
        stressed = with_extra_offsets(model, degrees)
        frozen_wins = (1 + model_correlations(stressed) @ signed.ravel()) / 2
        redesigned = search_tables(stressed)["winner"]
        rows.append({
            "extra_offset_deg": degrees,
            "frozen_worst_gap_pp": float(100 * (min(frozen_wins) - frozen["classical_win"])),
            "redesigned_worst_gap_pp": redesigned["worst_gap_pp"],
            "redesigned_weights": redesigned["weights"],
            "redesigned_target_parity": redesigned["target_parity"],
        })
    return rows


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("--model", type=Path, default=default_model)
    args = parser.parse_args(argv)
    model = json.loads(args.model.read_text(encoding="utf-8"))
    print(json.dumps(sweep(model), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
