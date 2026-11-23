"""Compare a frozen game with a redesigned game as one measurement drifts."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from run_search import model_correlations, search_tables


def sweep(model):
    frozen = search_tables(model)["winner"]
    weights = np.array(frozen["weights"])
    signed = weights * (1 - 2 * np.array(frozen["target_parity"])) / weights.sum()
    rows = []
    for degrees in range(0, 46, 5):
        scenarios = []
        for original in model["scenarios"]:
            for offset in sorted({-degrees, 0, degrees}):
                scenario = deepcopy(original)
                scenario["name"] += f"_offset_{offset:+d}"
                scenario["offset_b_deg"][1] += offset
                scenarios.append(scenario)
        stressed = {"settings": model["settings"], "scenarios": scenarios}
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path(__file__).with_name("model.json"))
    args = parser.parse_args()
    model = json.loads(args.model.read_text(encoding="utf-8"))
    print(json.dumps(sweep(model), indent=2, allow_nan=False))
