"""Replay the referee's question selection from a binary file of uniform bytes.

This offline audit log includes both questions and their target parity. A live
experiment would deliver only x to Alice and only y to Bob. No player answers
are generated or measured here. The caller supplies the randomness and its
provenance independently.
"""

import argparse
import json
from bisect import bisect_right
from itertools import accumulate
from pathlib import Path


def replay(weights, target_parity, stream, rounds, *, schedule="iid"):
    """Select questions in row-major weight order and return the referee log."""
    if schedule not in ("iid", "quota"):
        raise ValueError("schedule must be iid or quota")
    if not (schedule == "quota" and rounds is None) and (type(rounds) is not int or rounds < 0):
        raise ValueError("rounds must be a nonnegative integer")
    if not isinstance(weights, list) or not weights or not isinstance(weights[0], list):
        raise ValueError("weights must be a nonempty matrix")
    columns = len(weights[0])
    if not columns or any(
        not isinstance(row, list) or len(row) != columns or
        any(type(w) is not int or w <= 0 for w in row) for row in weights
    ):
        raise ValueError("weights must be a rectangular matrix of positive integers")
    if not isinstance(target_parity, list) or len(target_parity) != len(weights) or any(
        not isinstance(row, list) or len(row) != columns or
        any(type(p) is not int or p not in (0, 1) for p in row) for row in target_parity
    ):
        raise ValueError("target_parity must match weights and contain only 0 or 1")

    remaining = [w for row in weights for w in row]
    boundaries = list(accumulate(remaining))
    block_length = boundaries[-1]
    if schedule == "quota":
        rounds = block_length if rounds is None else rounds
        if rounds > block_length:
            raise ValueError("quota rounds cannot exceed one block")
    counts = [[0] * columns for _ in weights]
    log = []
    consumed = rejected = 0
    for _ in range(rounds):
        fixed_cell = None
        if schedule == "quota":
            # Distinguish a forced question from multiple copies of that question.
            active = [cell for cell, count in enumerate(remaining) if count]
            if len(active) == 1:
                fixed_cell = active[0]
            else:
                boundaries = list(accumulate(remaining))
        if fixed_cell is None:
            total_weight = boundaries[-1]
            width = max(1, ((total_weight - 1).bit_length() + 7) // 8)
            source_range = 1 << (8 * width)
            # Each accepted residue has exactly cutoff / total_weight preimages.
            cutoff = source_range - source_range % total_weight
            while True:
                block = stream.read(width)
                if len(block) != width:
                    raise ValueError(f"randomness file exhausted after {len(log)} of {rounds} rounds")
                consumed += width
                candidate = int.from_bytes(block, "big")
                if candidate < cutoff:
                    cell = bisect_right(boundaries, candidate % total_weight)
                    break
                rejected += width
        else:
            cell = fixed_cell
        if schedule == "quota":
            remaining[cell] -= 1
        x, y = divmod(cell, columns)
        counts[x][y] += 1
        log.append({"x": x, "y": y, "target_parity": target_parity[x][y]})
    audit = {
        "mode": "offline_referee_log",
        "round_count": rounds,
        "source_bytes_consumed": consumed,
        "source_bytes_rejected": rejected,
        "question_counts": counts,
        "referee_rounds": log,
    }
    if schedule == "quota":
        audit.update(schedule="quota", quota_block_length=block_length, quota_block_complete=rounds == block_length)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="game search result JSON")
    parser.add_argument("bits", type=Path, help="binary bytes, not a file of ASCII zeros and ones")
    parser.add_argument("--schedule", choices=("iid", "quota"), default="iid")
    parser.add_argument("--rounds", type=int, help="default: 30 IID rounds or one complete quota block")
    args = parser.parse_args()
    try:
        winner = json.loads(args.result.read_text(encoding="utf-8"))["winner"]
        with args.bits.open("rb") as stream:
            rounds = 30 if args.rounds is None and args.schedule == "iid" else args.rounds
            audit = replay(winner["weights"], winner["target_parity"], stream, rounds, schedule=args.schedule)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{parser.prog}: {error}\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
