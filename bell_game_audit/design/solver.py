"""Bias bounds for two-player XOR games with a real, signed payoff matrix.

If M[x,y] = p(x,y) (-1)**f(x,y), the winning probability is (1+bias)/2.
Matrices need not be normalized. All functions return biases or witnesses
in the same convention, including for rectangular games.
"""

from functools import lru_cache
from itertools import islice, product
from math import fsum
from operator import index

import numpy as np


def _matrix(matrix):
    raw = np.asarray(matrix)
    if raw.ndim != 2 or 0 in raw.shape or np.iscomplexobj(raw):
        raise ValueError("expected a nonempty real matrix")
    values = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("matrix entries must be finite")
    return values


@lru_cache(maxsize=12)
def _small_signs(size):
    # Reversing both players' signs leaves all products unchanged.
    suffix = list(product((-1.0, 1.0), repeat=size - 1))
    return np.column_stack((np.ones(len(suffix)), np.asarray(suffix)))


def classical_bias(matrix):
    """Maximize a.T @ M @ b exactly over deterministic sign strategies.

    For fixed a, Bob maximizes each column separately, yielding ||a.T M||_1.
    Enumerate the smaller side and use global sign symmetry to halve the work.
    The optimization is exhaustive; numerical values use float64 arithmetic.
    """
    values = _matrix(matrix)
    if values.shape[0] > values.shape[1]:
        values = values.T
    size = values.shape[0]
    if size <= 12:
        scores = np.abs(_small_signs(size) @ values).sum(axis=1)
        return float(scores.max())

    suffixes = product((-1.0, 1.0), repeat=size - 1)
    best = 0.0
    while batch := list(islice(suffixes, 1024)):
        signs = np.column_stack((np.ones(len(batch)), batch))
        best = max(best, np.abs(signs @ values).sum(axis=1).max())
    return float(best)


def _unit_response(fields, previous):
    lengths = np.hypot(fields[..., 0], fields[..., 1])[..., None]
    # An unconstrained response, including a zero-weight row, keeps its axis.
    return np.divide(fields, lengths, out=previous.copy(), where=lengths > 0)


def planar_witness(matrix, restarts=16, seed=0):
    """Return Alice and Bob unit axes, shaped (rows, 2) and (columns, 2).

    On |Phi+>, measuring u[0]*Z + u[1]*X and v[0]*Z + v[1]*X gives
    correlation u dot v. The score sum(M * (u @ v.T)) is achievable.
    Alternating best responses with multiple starts is a lower-bound heuristic.
    """
    values = _matrix(matrix)
    restarts = index(restarts)
    if restarts < 1:
        raise ValueError("restarts must be a positive integer")
    rows, columns = values.shape
    scale = np.max(np.abs(values))
    if scale > 0:
        values = values / scale
    rng = np.random.default_rng(seed)
    angles = rng.uniform(-np.pi, np.pi, (restarts, columns))
    angles[0] = np.pi * np.arange(columns) / columns
    bob = np.stack((np.cos(angles), np.sin(angles)), axis=-1)
    alice = np.zeros((restarts, rows, 2))
    alice[..., 0] = 1
    previous_scores = np.full(restarts, -np.inf)
    tolerance = 4e-15 * max(1.0, np.abs(values).sum())
    for _ in range(512):
        alice = _unit_response(values @ bob, alice)
        fields = values.T @ alice
        bob = _unit_response(fields, bob)
        scores = np.sum(fields * bob, axis=(1, 2))
        if np.max(np.abs(scores - previous_scores)) <= tolerance:
            break
        previous_scores = scores
    best = int(np.argmax(scores))
    return alice[best].copy(), bob[best].copy()


def _axes(vectors, count):
    axes = np.asarray(vectors)
    if axes.shape != (count, 2) or np.iscomplexobj(axes):
        raise ValueError(f"expected {count} real planar axes")
    axes = np.asarray(axes, dtype=np.float64)
    if not np.isfinite(axes).all() or not np.allclose(
        np.hypot(axes[:, 0], axes[:, 1]), 1, atol=1e-9, rtol=0
    ):
        raise ValueError("each axis must be a finite unit vector")
    return axes


def quantum_upper(matrix, u, v):
    """Numerical upper bound for all quantum XOR strategies, in any dimension.

    For H = [[0,M],[M.T,0]], every diagonal d with diag(d)-H PSD gives the
    Gram-SDP dual bound sum(d)/2. Start with planar best-response field norms,
    then shift the diagonal past the estimated minimum eigenvalue. The initial
    axes need not be optimal. A scale-dependent float64 guard covers ordinary
    eigensolver roundoff. This is a numerical bound, not an interval proof.
    Also use the triangle bound and the operator-norm bound obtained by
    Cauchy-Schwarz on the two stacks of unit vectors.
    """
    values = _matrix(matrix)
    rows, columns = values.shape
    alice, bob = _axes(u, rows), _axes(v, columns)
    scale = np.max(np.abs(values))
    if scale == 0:
        return 0.0
    scaled = values / scale
    left = scaled @ bob
    right = scaled.T @ alice
    d = np.concatenate((np.hypot(left[:, 0], left[:, 1]),
                        np.hypot(right[:, 0], right[:, 1])))
    slack = np.diag(d)
    slack[:rows, rows:] = -scaled
    slack[rows:, :rows] = -scaled.T
    size = rows + columns
    guard = 64 * np.finfo(float).eps * size * np.linalg.norm(slack, ord=np.inf)
    smallest = np.linalg.eigvalsh(slack)[0]
    shift = max(0.0, guard - smallest)
    dual_bound = float(scale) * (fsum(d) + size * shift) / 2
    active_rows = np.count_nonzero(values.any(axis=1))
    active_columns = np.count_nonzero(values.any(axis=0))
    norm_guard = 64 * np.finfo(float).eps * size * np.linalg.norm(scaled)
    operator_norm = np.linalg.norm(scaled, ord=2) + norm_guard
    spectral_bound = float(scale) * np.sqrt(active_rows * active_columns) * operator_norm
    return float(min(dual_bound, spectral_bound, fsum(np.abs(values).ravel())))
