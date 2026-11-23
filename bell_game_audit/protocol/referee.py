"""Replay the referee's question selection from a binary file of uniform bytes.

This offline audit log includes both questions and their target parity. A live
experiment would deliver only x to Alice and only y to Bob. No player answers
are generated or measured here. The caller supplies the randomness and its
provenance independently.
"""

import argparse
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import accumulate, chain
from pathlib import Path
from typing import BinaryIO

from ..design.verify import read_result
from ..resources import write_report


@dataclass(frozen=True, slots=True)
class _Game:
    """A validated game with row-major cumulative weights for sampling."""

    boundaries: tuple[int, ...]
    targets: tuple[tuple[int, ...], ...]

    @classmethod
    def from_matrices(cls, weights: list[list[int]], target_parity: list[list[int]]) -> "_Game":
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
        boundaries = tuple(accumulate(chain.from_iterable(weights)))
        return cls(boundaries, tuple(tuple(row) for row in target_parity))


@dataclass(frozen=True, slots=True)
class _DrawState:
    """All quantities needed to interpret the next uniform candidate."""

    boundaries: tuple[int, ...]
    quota: bool
    byte_width: int
    cutoff: int
    forced_cell: int | None

    @classmethod
    def from_boundaries(cls, boundaries: tuple[int, ...], quota: bool) -> "_DrawState":
        total = boundaries[-1]
        if total == 0:
            return cls(boundaries, quota, 0, 0, None)
        if quota:
            first = bisect_right(boundaries, 0)
            if boundaries[first] == total:
                return cls(boundaries, quota, 0, 0, first)
        width = max(1, ((total - 1).bit_length() + 7) // 8)
        source_range = 1 << (8 * width)
        return cls(boundaries, quota, width, source_range - source_range % total, None)

    def step(self, candidate: int | None) -> tuple[int, "_DrawState"] | None:
        """Return the selected cell and next state, or None for a rejected proposal.

        A forced quota draw takes None as its input and consumes no randomness.
        """
        total = self.boundaries[-1]
        if not total:
            raise ValueError("quota block exhausted")
        if self.forced_cell is not None:
            if candidate is not None:
                raise ValueError("a forced quota draw takes no candidate")
            cell = self.forced_cell
        else:
            if type(candidate) is not int or candidate < 0 or candidate.bit_length() > 8 * self.byte_width:
                raise ValueError("candidate does not fit the required byte width")
            # Every accepted residue has the same number of preimages.
            if candidate >= self.cutoff:
                return None
            cell = bisect_right(self.boundaries, candidate % total)

        if not self.quota:
            return cell, self
        # Removing one copy shifts only the cumulative bounds from this cell on.
        remaining = self.boundaries[:cell] + tuple(bound - 1 for bound in self.boundaries[cell:])
        return cell, _DrawState.from_boundaries(remaining, quota=True)


def _read_candidate(stream: BinaryIO, width: int) -> int | None:
    """Read exactly one proposal, handling short reads without reading ahead."""
    block = stream.read(width)
    if len(block) == width:
        return int.from_bytes(block, "big")
    partial = bytearray(block)
    while block and len(partial) < width:
        block = stream.read(width - len(partial))
        partial.extend(block)
    return int.from_bytes(partial, "big") if len(partial) == width else None


def replay(
    weights: list[list[int]], target_parity: list[list[int]], stream: BinaryIO,
    rounds: int | None, *, schedule: str = "iid",
) -> dict[str, object]:
    """Select questions in row-major weight order and return the referee log."""
    if schedule not in ("iid", "quota"):
        raise ValueError("schedule must be iid or quota")
    quota = schedule == "quota"
    game = _Game.from_matrices(weights, target_parity)
    block_length = game.boundaries[-1]
    if quota and rounds is None:
        rounds = block_length
    if type(rounds) is not int or rounds < 0:
        raise ValueError("rounds must be a nonnegative integer")
    if quota and rounds > block_length:
        raise ValueError("quota rounds cannot exceed one block")

    state = _DrawState.from_boundaries(game.boundaries, quota)
    columns = len(game.targets[0])
    counts = [[0] * columns for _ in game.targets]
    log = []
    consumed = rejected = 0
    while len(log) < rounds:
        candidate = None
        if state.byte_width:
            candidate = _read_candidate(stream, state.byte_width)
            if candidate is None:
                raise ValueError(f"randomness file exhausted after {len(log)} of {rounds} rounds")
            consumed += state.byte_width
        transition = state.step(candidate)
        if transition is None:
            rejected += state.byte_width
            continue
        cell, state = transition
        x, y = divmod(cell, columns)
        counts[x][y] += 1
        log.append({"x": x, "y": y, "target_parity": game.targets[x][y]})

    audit = {
        "mode": "offline_referee_log",
        "round_count": rounds,
        "source_bytes_consumed": consumed,
        "source_bytes_rejected": rejected,
        "question_counts": counts,
        "referee_rounds": log,
    }
    if quota:
        audit.update(schedule="quota", quota_block_length=block_length, quota_block_complete=rounds == block_length)
    return audit


def main(argv: Sequence[str] | None = None, *, prog: str | None = None) -> None:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument("result", type=Path, help="game search result JSON")
    parser.add_argument("bits", type=Path, help="binary bytes, not a file of ASCII zeros and ones")
    parser.add_argument("--schedule", choices=("iid", "quota"), default="iid")
    parser.add_argument("--rounds", type=int, help="default: 30 IID rounds or one complete quota block")
    args = parser.parse_args(argv)
    try:
        winner = read_result(args.result)["winner"]
        with args.bits.open("rb") as stream:
            rounds = 30 if args.rounds is None and args.schedule == "iid" else args.rounds
            audit = replay(winner["weights"], winner["target_parity"], stream, rounds, schedule=args.schedule)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{parser.prog}: {error}\n")
    write_report(audit)


if __name__ == "__main__":
    main()
