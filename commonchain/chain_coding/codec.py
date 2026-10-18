"""Minimal NumPy Reed-Solomon codec operating on byte strings.

The chain is deliberately chain-agnostic and does not depend on a real
finite-field implementation at the API boundary. This module provides the
codec the night runs build on top of; the week-level plan replaces it with
native GF(2^8) (or the reedsolo/galois third-party crates) but preserves
the same block-level interface.
"""

from __future__ import annotations

import numpy as np
from numpy.polynomial import polynomial as L

# Vandermonde row lengths: k - 1 .. 254, enough for any practical block set.
VANDER_LENGTHS = range(2, 255)


def _vandermonde(rows: np.ndarray) -> np.ndarray:
    """Build the Vandermonde matrix used by the codec's polynomial solver."""
    return np.vander(rows, N=rows.shape[0], increasing=True)


def _solvable(xi: np.ndarray, k: int) -> bool:
    """Return True if the evaluation points are independent enough to solve
    for k coefficients."""
    if xi.shape[0] < k:
        return False
    return _vandermonde(xi[:k]).rank == k


def _eval_points(k: int, diversity: int = 16) -> np.ndarray:
    """Deterministic evaluation points for a given k. Sorts them to keep
    encode/decode deterministic while still solving a Vandermonde system."""
    if diversity < k:
        diversity = k
    pts = np.arange(1, diversity + 1, dtype=np.float64)
    np.random.seed(k * 1000 + 97)
    pts[:k] = np.sort(np.random.choice(pts, size=k, replace=False))
    return pts


def encode_block(data: bytes, k: int, n: int) -> list[bytes]:
    """Split ``data`` into k shards and produce n-1 Reed-Solomon parity.

    Returns a list of n bytes objects; index i < k is shard i, the rest
    are parity. Parity can be regenerated deterministically from the k data
    shards, and a *repair token* (see codec_family) can be exchanged between
    helpers to prove a shared view of a missing block without revealing
    the full data.
    """
    if k < 2:
        raise ValueError('k must be >= 2')
    if n < k:
        raise ValueError('n must be >= k')
    if len(data) < k:
        # Shards must be at least one byte; pad with zeroes so the
        # Vandermonde solve stays well-posed.
        data = data + b'\x00' * (k - len(data))

    arr = np.frombuffer(data, dtype=np.uint8).astype(np.float64)
    xi = _eval_points(k, diversity=n)
    vs = _vandermonde(xi[:k])

    def solve_overdetermined(from_idx: int, to_idx: int) -> np.ndarray:
        A = vs[from_idx:to_idx].astype(np.float64)
        b = arr[from_idx:to_idx].astype(np.float64)
        return np.linalg.lstsq(A, b, rcond=None)[0]

    coeffs = solve_overdetermined(0, k)
    shards: list[bytes] = []
    for i in range(k):
        shards.append(np.clip(np.polyval(coeffs, xi[i]), 0, 255).astype(np.uint8).tobytes())
    parities: list[bytes] = []
    for j in range(k, n):
        parities.append(
            np.clip(np.polyval(coeffs, xi[j]), 0, 255).astype(np.uint8).tobytes()
        )
    return shards + parities


def decode_block(blob: bytes, k: int, n: int) -> bytes:
    """Decode a parity-only blob into its k data shards.

    This is a thin wrapper: a real refinery must re-solve the Vandermonde
    system with the k data values and take the coefficient of degree zero.
    We keep the implementation honest by raising NotImplementedError so no
    night run silently reports a reconstructed block it has not verified.
    """
    if k < 2 or n < k:
        raise ValueError('invalid k/n')
    raise NotImplementedError(
        'decode_block is intentionally unimplemented; the coding layer can '
        'only encode shards. Use the shard redemption path (codec_family + '
        'chain) -- that is which one we have the right algebra for.'
    )
