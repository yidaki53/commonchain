"""GF(2^8) arithmetic and Reed-Solomon codec over the binary field.

True finite-field algebra for the Reed-Solomon code family. Uses the
primitive polynomial 0x11D (x^8 + x^4 + x^3 + x^2 + 1), the same as
AES/Rijndael and most RS implementations.

All operations are byte-oriented: each byte position across the k data
shards forms one independent GF(2^8) codeword, so a block of L bytes per
shard yields L independent RS codewords of length n.
"""

from __future__ import annotations

import numpy as np

_PRIMITIVE_POLY = 0x11D
_EXP: list[int] = [0] * 512
_LOG: list[int] = [0] * 256

# Threshold (bytes) above which the NumPy/CuPy vectorized path is used.
CUDA_THRESHOLD = 16384


def _init_tables() -> None:
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= _PRIMITIVE_POLY
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tables()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("gf_div by zero")
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def gf_inv(a: int) -> int:
    if a == 0:
        raise ZeroDivisionError("gf_inv of zero")
    return _EXP[(255 - _LOG[a]) % 255]


def gf_pow(a: int, n: int) -> int:
    if a == 0:
        return 0
    return _EXP[(_LOG[a] * n) % 255]


def _eval_points(n: int) -> list[int]:
    return list(range(1, n + 1))


# ---------------------------------------------------------------------------
# NumPy GF(2^8) multiplication table (Tier 2 vectorization)
# ---------------------------------------------------------------------------

_GF_MUL_TABLE: np.ndarray | None = None


def _ensure_gf_table() -> np.ndarray:
    """Lazily build a 256x256 GF(2^8) multiplication table as uint8."""
    global _GF_MUL_TABLE
    if _GF_MUL_TABLE is None:
        table = np.zeros((256, 256), dtype=np.uint8)
        for a in range(256):
            for b in range(256):
                table[a, b] = gf_mul(a, b)
        _GF_MUL_TABLE = table
    return _GF_MUL_TABLE


def gf_mul_vec(a_arr: np.ndarray, b: int) -> np.ndarray:
    """Multiply every byte of ``a_arr`` by scalar ``b`` in GF(2^8)."""
    return _ensure_gf_table()[a_arr, b]


def gf_mul_mat_vec(a_arr: np.ndarray, b_arr: np.ndarray) -> np.ndarray:
    """Elementwise GF(2^8) multiply of two equal-shaped byte arrays."""
    return _ensure_gf_table()[a_arr, b_arr]


# ---------------------------------------------------------------------------
# NumPy vectorized RS encode (Tier 2)
# ---------------------------------------------------------------------------

def _rs_encode_shards_numpy(data_shards: list[bytes], n: int, k: int) -> list[bytes]:
    """Vectorized RS encode using the GF(2^8) lookup table.

    Stacks all data shards into a (k, length) uint8 array and applies the
    same row operations to every byte position simultaneously via NumPy
    vectorization.
    """
    length = len(data_shards[0])
    data = np.frombuffer(b"".join(data_shards), dtype=np.uint8).reshape(k, length)
    xi = _eval_points(n)
    shards = np.zeros((n, length), dtype=np.uint8)

    for j in range(n):
        xj = xi[j]
        # Precompute xj^i once per evaluation point (not per byte).
        xj_powers = [1] * k
        for i in range(1, k):
            xj_powers[i] = gf_mul(xj_powers[i - 1], xj)
        acc = np.zeros(length, dtype=np.uint8)
        for i in range(k):
            acc ^= gf_mul_vec(data[i], xj_powers[i])
        shards[j] = acc

    return [shards[j].tobytes() for j in range(n)]


# ---------------------------------------------------------------------------
# CuPy GPU RS encode (Tier 4, only for blocks >= CUDA_THRESHOLD)
# ---------------------------------------------------------------------------

def _rs_encode_shards_cupy(data_shards: list[bytes], n: int, k: int) -> list[bytes]:
    """GPU-accelerated RS encode via CuPy.

    Only worthwhile for large blocks (>= CUDA_THRESHOLD bytes) where the
    host<->device transfer cost is amortized. Falls back to NumPy if CuPy
    is not importable.
    """
    try:
        import cupy as cp
    except ImportError:
        return _rs_encode_shards_numpy(data_shards, n, k)

    length = len(data_shards[0])
    data = cp.asarray(
        np.frombuffer(b"".join(data_shards), dtype=np.uint8).reshape(k, length)
    )
    xi = _eval_points(n)
    shards = cp.zeros((n, length), dtype=cp.uint8)

    # Build GF mul table on GPU.
    gf_table = cp.zeros((256, 256), dtype=cp.uint8)
    for a in range(256):
        for b in range(256):
            gf_table[a, b] = gf_mul(a, b)

    for j in range(n):
        xj = xi[j]
        xj_powers = [1] * k
        for i in range(1, k):
            xj_powers[i] = gf_mul(xj_powers[i - 1], xj)
        acc = cp.zeros(length, dtype=cp.uint8)
        for i in range(k):
            acc ^= gf_table[data[i], xj_powers[i]]
        shards[j] = acc

    cp.get_default_stream().synchronize()
    return [cp.asnumpy(shards[j]).tobytes() for j in range(n)]


def rs_encode_shards(data_shards: list[bytes], n: int, k: int) -> list[bytes]:
    """Non-systematic RS: all n shards are evaluations p(xi[j]).

    The k data shards are treated as polynomial coefficients c_0..c_{k-1}.
    Each byte position b forms an independent codeword: p_b(xi[j]) for
    j = 0..n-1. Returns n shards, all evaluations (none is the raw data).

    Dispatch:
      * blocks >= CUDA_THRESHOLD bytes: CuPy GPU path (or NumPy fallback)
      * smaller blocks: pure-Python path (avoids array conversion overhead)
    """
    if k < 2:
        raise ValueError("k must be >= 2")
    if n < k:
        raise ValueError("n must be >= k")
    if not data_shards:
        raise ValueError("at least one data shard required")
    length = len(data_shards[0])
    for s in data_shards:
        if len(s) != length:
            raise ValueError("all data shards must have the same length")

    if length >= CUDA_THRESHOLD:
        return _rs_encode_shards_cupy(data_shards, n, k)

    xi = _eval_points(n)
    shards: list[bytearray] = [bytearray(length) for _ in range(n)]

    for j in range(n):
        xj = xi[j]
        # Precompute xj^i once per evaluation point (Tier 1 optimization).
        xj_powers = [1] * k
        for i in range(1, k):
            xj_powers[i] = gf_mul(xj_powers[i - 1], xj)
        for b in range(length):
            # p_b(xj) = sum_{i=0}^{k-1} c_i * xj^i
            acc = 0
            for i in range(k):
                acc ^= gf_mul(data_shards[i][b], xj_powers[i])
            shards[j][b] = acc

    return [bytes(s) for s in shards]


def _rs_decode_from_available_python(
    available: dict[int, bytes], k: int, n: int
) -> list[bytes]:
    """Pure-Python RS decode: per-byte Gauss-Jordan on the Vandermonde system.

    ``available`` maps shard_index -> shard bytes (evaluations at xi[idx]).
    Reconstructs the k data coefficients. Kept as the reference
    implementation for small blocks; large blocks go through
    ``_rs_decode_from_available_numpy``.
    """
    if len(available) < k:
        raise ValueError(f"need at least {k} shards, got {len(available)}")

    xi = _eval_points(n)
    indices = sorted(available.keys())[:k]
    length = len(available[indices[0]])

    data_shards: list[bytearray] = [bytearray(length) for _ in range(k)]

    for b in range(length):
        mat: list[list[int]] = []
        for t, idx in enumerate(indices):
            x = xi[idx]
            row = []
            xp = 1
            for i in range(k):
                row.append(xp)
                xp = gf_mul(xp, x)
            row.append(available[idx][b])
            mat.append(row)

        for col in range(k):
            pivot_row = None
            for r in range(col, k):
                if mat[r][col] != 0:
                    pivot_row = r
                    break
            if pivot_row is None:
                raise ValueError(f"singular Vandermonde matrix at byte {b}")

            mat[col], mat[pivot_row] = mat[pivot_row], mat[col]

            inv = gf_inv(mat[col][col])
            for j in range(col, k + 1):
                mat[col][j] = gf_mul(mat[col][j], inv)

            for r in range(k):
                if r != col and mat[r][col] != 0:
                    factor = mat[r][col]
                    for j in range(col, k + 1):
                        mat[r][j] ^= gf_mul(factor, mat[col][j])

        for i in range(k):
            data_shards[i][b] = mat[i][k]

    return [bytes(s) for s in data_shards]


def _rs_decode_from_available_numpy(
    available: dict[int, bytes], k: int, n: int
) -> list[bytes]:
    """Vectorized RS decode: Gauss-Jordan on the scalar Vandermonde matrix,
    then apply the inverse to all byte positions simultaneously via NumPy.

    Instead of running per-byte Gauss-Jordan (O(length * k^2) Python ops),
    we invert the (k x k) Vandermonde matrix once and multiply it against
    the stacked (k, length) evaluation tensor using GF(2^8) vectorized ops.
    """
    if len(available) < k:
        raise ValueError(f"need at least {k} shards, got {len(available)}")

    xi = _eval_points(n)
    indices = sorted(available.keys())[:k]
    length = len(available[indices[0]])

    # Build Vandermonde matrix V[i][j] = xi[indices[i]]^j  (k x k)
    V = np.zeros((k, k), dtype=np.uint8)
    for i, idx in enumerate(indices):
        x = xi[idx]
        xp = 1
        for j in range(k):
            V[i, j] = xp
            xp = gf_mul(xp, x)

    # Gauss-Jordan invert V: augment with identity [V | I] -> [I | V^-1]
    table = _ensure_gf_table()
    aug = np.concatenate([V, np.eye(k, dtype=np.uint8)], axis=1)
    for col in range(k):
        pivot_row = None
        for r in range(col, k):
            if aug[r, col] != 0:
                pivot_row = r
                break
        if pivot_row is None:
            raise ValueError("singular Vandermonde matrix")
        if pivot_row != col:
            aug[[col, pivot_row]] = aug[[pivot_row, col]]
        inv = gf_inv(int(aug[col, col]))
        aug[col] = table[aug[col], inv]
        for r in range(k):
            if r != col and aug[r, col] != 0:
                factor = int(aug[r, col])
                aug[r] = aug[r] ^ table[aug[col], factor]

    V_inv = aug[:, k:]

    # Stack evaluations into (k, length): y[i, b] = available[indices[i]][b]
    y = np.zeros((k, length), dtype=np.uint8)
    for i, idx in enumerate(indices):
        y[i] = np.frombuffer(available[idx], dtype=np.uint8)

    # c = V_inv @ y over GF(2^8): c[i] = XOR_j gf_mul_vec(y[j], V_inv[i,j])
    c = np.zeros((k, length), dtype=np.uint8)
    for i in range(k):
        for j in range(k):
            coeff = int(V_inv[i, j])
            if coeff != 0:
                c[i] ^= table[y[j], coeff]

    return [c[i].tobytes() for i in range(k)]


def rs_decode_from_available(
    available: dict[int, bytes], k: int, n: int
) -> list[bytes]:
    """Reconstruct k coefficient shards from any k available evaluation shards.

    ``available`` maps shard_index -> shard bytes (evaluations at xi[idx]).
    Uses Gauss-Jordan elimination over GF(2^8) to solve the Vandermonde
    system and recover the k data coefficients.

    For blocks >= 4 KiB, dispatches to a NumPy-vectorized path that inverts
    the Vandermonde matrix once and applies it to all byte positions at once.
    """
    if len(available) < k:
        raise ValueError(f"need at least {k} shards, got {len(available)}")

    length = len(next(iter(available.values())))
    if length >= 4096:
        return _rs_decode_from_available_numpy(available, k, n)

    return _rs_decode_from_available_python(available, k, n)


def rs_solve_partial(
    known_coeffs: dict[int, bytes],
    evals: dict[int, bytes],
    k: int,
) -> list[bytes]:
    """Recover all k coefficient shards from partial knowledge.

    ``known_coeffs`` maps coefficient indices (0..k-1) to their known
    bytes. ``evals`` maps evaluation points ``x`` (non-zero GF(256)
    elements, plain ints) to evaluation shard bytes, where for every byte
    position ``b``::

        evals[x][b] = sum_{i=0}^{k-1} c_i[b] * x^i   (over GF(256))

    Solves the mixed linear system: each evaluation at a distinct point
    gives one equation per byte for the unknown coefficients (known
    coefficients are substituted on the right-hand side). Needs at least
    as many distinct evaluation points as unknown coefficients.
    Returns the k coefficient shards c_0..c_{k-1} in index order.
    Raises ValueError when underdetermined or singular.
    """
    missing = [i for i in range(k) if i not in known_coeffs]
    m = len(missing)
    if m == 0:
        return [bytes(known_coeffs[i]) for i in range(k)]
    if len(evals) < m:
        raise ValueError(
            f"need {m} evaluations for {m} unknown coefficients, got {len(evals)}"
        )
    xs = sorted(evals.keys())[:m]
    length = len(evals[xs[0]])
    for x in xs:
        if len(evals[x]) != length:
            raise ValueError("all evaluation shards must have the same length")
    for v in known_coeffs.values():
        if len(v) != length:
            raise ValueError("known coefficients and evaluations length mismatch")

    solved: dict[int, bytearray] = {}
    for b in range(length):
        mat: list[list[int]] = []
        for x in xs:
            # powers[i] = x^i for i = 0..k-1
            powers = [1] * k
            for i in range(1, k):
                powers[i] = gf_mul(powers[i - 1], x)
            rhs = evals[x][b]
            for i in known_coeffs:
                rhs ^= gf_mul(known_coeffs[i][b], powers[i])
            mat.append([powers[i] for i in missing] + [rhs])

        for col in range(m):
            pivot_row = None
            for r in range(col, m):
                if mat[r][col] != 0:
                    pivot_row = r
                    break
            if pivot_row is None:
                raise ValueError(f"singular partial Vandermonde at byte {b}")

            mat[col], mat[pivot_row] = mat[pivot_row], mat[col]

            inv = gf_inv(mat[col][col])
            for j in range(col, m + 1):
                mat[col][j] = gf_mul(mat[col][j], inv)

            for r in range(m):
                if r != col and mat[r][col] != 0:
                    factor = mat[r][col]
                    for j in range(col, m + 1):
                        mat[r][j] ^= gf_mul(factor, mat[col][j])

        for i in range(m):
            idx = missing[i]
            if idx not in solved:
                solved[idx] = bytearray(length)
            solved[idx][b] = mat[i][m]

    result: list[bytes] = []
    for i in range(k):
        if i in known_coeffs:
            result.append(bytes(known_coeffs[i]))
        else:
            result.append(bytes(solved[i]))
    return result
