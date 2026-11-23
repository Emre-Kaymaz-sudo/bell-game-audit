"""Construct exact small-deck local loss bounds from regular subdecks.

A uniform rectangle uses independent cyclic relabelings on the two sides.
A six-cycle uses simultaneous relabelings from S3 after mapping its missing
matching to the diagonal. Both constructions simulate private question
histories conditional on the current question pair. Therefore each such
subdeck costs its ordinary one-round minimum number of losses.

For positive 3-by-3 integer quotas totaling at most 27, find_packing maximizes
the sum of those losses over integer packings. Leftovers are singleton decks.
Equality with the full deck's one-round loss proves private-history equality.
A lower total is only a bound for this family of constructions.
"""

from collections import Counter
from functools import lru_cache
from itertools import combinations, permutations, product
from operator import index


def _table(values, label, low, high):
    if len(values) != 3 or any(len(row) != 3 for row in values):
        raise ValueError(f"{label} must be a 3-by-3 integer matrix")
    result = []
    for row in values:
        for item in row:
            if isinstance(item, bool) or getattr(getattr(item, "dtype", None), "kind", "") == "b":
                raise ValueError(f"{label} cannot contain booleans")
            try:
                value = index(item)
            except TypeError as exc:
                raise ValueError(f"{label} must contain integers") from exc
            if not low <= value <= high:
                raise ValueError(f"{label} values must lie between {low} and {high}")
            result.append(value)
    return tuple(result)


@lru_cache(maxsize=512)
def _loss_sets(parity):
    # Enumerate all deterministic error patterns up to the global XOR flip.
    # Inclusion-nonminimal sets never improve a nonnegative loss objective.
    masks = set()
    for bits in product((0, 1), repeat=5):
        alice, bob = (0,) + bits[:2], bits[2:]
        errors = frozenset(i for i, target in enumerate(parity)
                           if alice[i // 3] ^ bob[i % 3] ^ target)
        masks.add(errors)
    return tuple(sorted((tuple(sorted(m)) for m in masks if not any(s < m for s in masks)),
                        key=lambda m: (len(m), m)))


def _best_static(counts, error_sets):
    return min((sum(counts[i] for i in errors), errors) for errors in error_sets)


@lru_cache(maxsize=512)
def _subdecks(parity):
    supports = set()
    for height, width in ((3, 3), (2, 3), (3, 2), (2, 2)):
        for rows in combinations(range(3), height):
            for cols in combinations(range(3), width):
                supports.add(tuple(3 * x + y for x in rows for y in cols))
    for missing in permutations(range(3)):
        supports.add(tuple(i for i in range(9) if i % 3 != missing[i // 3]))

    valued = []
    for support in supports:
        loss = min(sum(i in support for i in errors) for errors in _loss_sets(parity))
        if loss:
            valued.append((support, loss))
    return tuple(sorted(valued, key=lambda entry: (-entry[1], len(entry[0]), entry[0])))


def find_packing(weights, target_parity):
    """Return a complete list of (sorted tuple of (x, y) cells, copies).

    The packed loss is maximal over uniform 2x2, 2x3, 3x2, and 3x3 rectangles
    and over six-cycle complements of perfect matchings, with singleton fill.
    The search is exact. It rejects decks outside the size cap before searching.
    """
    counts = _table(weights, "weights", 1, 27)
    if sum(counts) > 27:
        raise ValueError("exact 3-by-3 packing is limited to 27 cards")
    parity = _table(target_parity, "target_parity", 0, 1)
    error_sets = _loss_sets(parity)
    candidates = _subdecks(parity)
    by_cell = [[(support, loss) for support, loss in candidates if i in support] for i in range(9)]

    @lru_cache(maxsize=None)
    def reach(remaining, target):
        if target <= 0:
            return ()
        upper, errors = _best_static(remaining, error_sets)
        slack = upper - target
        if slack < 0:
            return None

        # Every optimal static strategy loses on these 'errors' cells. Pick
        # one remaining copy. Any admissible packing must put that very copy
        # into a candidate subdeck containing it, or leave it as a singleton.
        # A subdeck spending k such cells for l certified losses consumes
        # k-l units of the available slack.
        best_options = None
        for i in errors:
            if remaining[i] == 0:
                continue
            options = [(support, loss) for support, loss in by_cell[i]
                       if sum(cell in errors for cell in support) - loss <= slack
                       and all(remaining[cell] for cell in support)]
            if slack:
                options.append(((i,), 0))
            if not options:
                return None
            if best_options is None or len(options) < len(best_options):
                best_options = options
        for support, loss in best_options:
            child = list(remaining)
            for i in support:
                child[i] -= 1
            tail = reach(tuple(child), target - loss)
            if tail is not None:
                return (support,) + tail
        return None

    # No packing can exceed any fixed response's losses. Try targets from
    # this upper bound downward, stopping as soon as a packing attains one.
    upper, _ = _best_static(counts, error_sets)
    for target in range(upper, -1, -1):
        packed = reach(counts, target)
        if packed is not None:
            break
    reach.cache_clear()
    used = Counter(packed)
    leftovers = list(counts)
    for support, copies in used.items():
        for i in support:
            leftovers[i] -= copies
    for i, copies in enumerate(leftovers):
        if copies:
            used[(i,)] += copies
    return [(tuple(divmod(i, 3) for i in support), copies)
            for support, copies in sorted(used.items(), key=lambda item: (-len(item[0]), item[0]))]
