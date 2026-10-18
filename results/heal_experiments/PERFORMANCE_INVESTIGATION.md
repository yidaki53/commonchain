# Performance Investigation: Codec Layer Optimization

## Executive Summary

The codec layer (`commonchain/chain_coding/`) is pure Python with NumPy used
only in the legacy `codec.py` (not on the hot path). The true algebraic
backends (`gf256.py`, `fountain.py`, `lrc.py`) use byte-by-byte Python loops
for GF(2^8) arithmetic and XOR operations. For typical shard sizes (1-64 KB),
this is acceptable (<1ms repair), but at scale (MB+ blocks, high throughput)
the Python-level loops become the dominant cost.

**No Cython, no CUDA, no GPU code exists in the repo.** NumPy is a declared
dependency but only used by `codec.py` (float64 Vandermonde, not GF(2^8)).

---

## 1. Hot Path Analysis

### 1.1 `gf256.rs_encode_shards` — THE BIGGEST BOTTLENECK

**File:** `commonchain/chain_coding/gf256.py`, lines 85-94

```python
for j in range(n):
    xj = xi[j]
    for b in range(length):
        # p_b(xj) = sum_{i=0}^{k-1} c_i * xj^i
        acc = 0
        xj_pow = 1
        for i in range(k):
            acc ^= gf_mul(data_shards[i][b], xj_pow)
            xj_pow = gf_mul(xj_pow, xj)
        shards[j][b] = acc
```

**Complexity:** O(n × length × k) Python-level GF multiply operations.
For a 64 KB block with k=3, n=5: 5 × 65536 × 3 ≈ 1M Python byte operations
plus 2M `gf_mul` calls (each a dict/list lookup + XOR).

This is called for every global parity shard in LRC (`lrc.py` line 112) and
for every RS encode/decode.

### 1.2 `gf256.rs_decode_from_available` — Gauss-Jordan per byte

**File:** `commonchain/chain_coding/gf256.py`, lines 115-153

For each byte position `b` (0..length-1), runs full Gauss-Jordan elimination
over GF(2^8) on a k×(k+1) matrix. **Complexity:** O(length × k^3) Python
operations. For length=65536, k=3: 65536 × 27 ≈ 1.8M Python operations.

### 1.3 `lrc.lrc_encode_shards` — local parity XOR

**File:** `commonchain/chain_coding/lrc.py`, lines 103-108

```python
for group in groups:
    local_parity = bytearray(length)
    for j in group:
        src = data_shards[j]
        for b in range(length):
            local_parity[b] ^= src[b]
```

**Complexity:** O(groups × group_size × length) Python byte XOR operations.
For k=3, gs=2, length=65536: ~2 groups × 2 members × 65536 ≈ 262K XOR ops.

### 1.4 `fountain.fountain_encode_shards` — random subset XOR

**File:** `commonchain/chain_coding/fountain.py`, lines 68-71

```python
for idx in source_indices:
    src = data_shards[idx]
    for b in range(length):
        out[b] ^= src[b]
```

---

## 2. Optimization Roadmap

### Tier 1: Pythonic Quick Wins (no new deps, <1 hour)

#### 2.1 Replace byte-by-byte XOR with `int.from_bytes` XOR

For XORing multiple byte strings of equal length, converting to big integers,
XORing, and converting back is **5-10x faster** than Python byte loops for
shards >256 bytes:

```python
# CURRENT (slow):
for b in range(length):
    local_parity[b] ^= src[b]

# FASTER (pure Python):
acc = 0
for src in shards_in_group:
    acc ^= int.from_bytes(src, 'big')
local_parity = acc.to_bytes(length, 'big')
```

**Files to change:** `lrc.py` (lines 103-108, 146-153), `fountain.py` (lines 68-71, 129-132)

#### 2.2 Precompute GF(2^8) powers per evaluation point

In `rs_encode_shards`, `xj_pow = gf_mul(xj_pow, xj)` is computed inside the
byte loop but is independent of `b`. Precompute `xj_powers[i] = xj^i` once
per evaluation point (~30% of encode cost):

```python
xj_powers = [1] * k
for i in range(1, k):
    xj_powers[i] = gf_mul(xj_powers[i-1], xj)
for b in range(length):
    acc = 0
    for i in range(k):
        acc ^= gf_mul(data_shards[i][b], xj_powers[i])
    shards[j][b] = acc

---

### Tier 2: NumPy Vectorization (numpy already a dep, 1-2 days)

#### 2.3 GF(2^8) multiplication as NumPy lookup table

Build a 256×256 `uint8` multiplication table:

```python
import numpy as np
_GF_MUL_TABLE = np.zeros((256, 256), dtype=np.uint8)
for a in range(256):
    for b in range(256):
        _GF_MUL_TABLE[a, b] = gf_mul(a, b)
```

Vectorized GF multiply across all byte positions:

```python
def gf_mul_vec(a_arr: np.ndarray, b: int) -> np.ndarray:
    """Multiply every byte of a_arr by scalar b in GF(2^8)."""
    return _GF_MUL_TABLE[a_arr, b]
```

#### 2.4 Vectorized RS encode

Replaces O(n × k × length) Python GF multiplies with O(n × k) NumPy vector
operations. Expected **20-50x speedup** on encode:

```python
def rs_encode_shards_numpy(data_shards, n, k):
    length = len(data_shards[0])
    data = np.frombuffer(b''.join(data_shards), dtype=np.uint8).reshape(k, length)
    xi = _eval_points(n)
    shards = np.zeros((n, length), dtype=np.uint8)
    for j in range(n):
        xj = xi[j]
        xj_powers = [1] * k
        for i in range(1, k):
            xj_powers[i] = gf_mul(xj_powers[i-1], xj)
        acc = np.zeros(length, dtype=np.uint8)
        for i in range(k):
            acc ^= gf_mul_vec(data[i], xj_powers[i])
        shards[j] = acc
    return [shards[j].tobytes() for j in range(n)]
```

#### 2.5 Vectorized LRC XOR

`np.bitwise_xor.reduce` replaces the Python XOR loop entirely:

```python
for group in groups:
    local_parity = np.bitwise_xor.reduce(data[list(group)])
    shards.append(local_parity.tobytes())
```

#### 2.6 Vectorized RS decode (harder)

Gauss-Jordan elimination is sequential per column but parallel across byte
positions. Process chunks of 1024 byte positions simultaneously. Expected
**10-30x speedup** on decode.

**Files to change:** `gf256.py` (add `_GF_MUL_TABLE`, vectorized variants), `lrc.py`, `fountain.py`

---

### Tier 3: Cython (2-3 days, new build dependency: Cython)

Create `.pyx` files for the three hot modules with typed memoryviews:

```cython
# gf256.pyx
import numpy as np
cimport numpy as cnp

cnp.import_array()

_PRIMITIVE_POLY = 0x11D
_EXP: np.ndarray[cnp.uint8_t, ndim=1] = np.zeros(512, dtype=np.uint8)
_LOG: np.ndarray[cnp.uint8_t, ndim=1] = np.zeros(256, dtype=np.uint8)

cpdef unsigned char gf_mul(unsigned char a, unsigned char b) nogil:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]
```

With `nogil` for pure computation and typed `unsigned char` for GF elements,
inner loops run at C speed. Expected **50-100x speedup** on GF arithmetic.

**Build setup:** Add `cythonize` to `pyproject.toml` build-system, compile
`gf256.pyx`, `lrc.pyx`, `fountain.pyx` as extension modules.

---

### Tier 4: CUDA / GPU (3-5 days, new dependency: cupy or numba[cuda])

GF(2^8) arithmetic is **embarrassingly parallel across byte positions** — each
byte is an independent GF(2^8) codeword:

| Factor | Assessment |
|--------|-----------|
| Parallelism | Excellent — byte positions are independent |
| Memory transfer | Host↔device transfer dominates for small shards (<4 KB). Wins only for large blocks (>16 KB) |
| Library | `cupy` (NumPy-like GPU API) or `numba[cuda]` |
| GF tables on GPU | 256×256 mul table fits in constant memory |
| Expected speedup | 10-100x for large blocks, 0.5-2x for small blocks (transfer bound) |

**Recommendation:** Only pursue CUDA if blocks routinely exceed 16 KB and
throughput is a proven bottleneck. For the current <1ms repair times, CPU
optimization (Tiers 1-3) is sufficient.

---

## 3. Recommended Action Plan

| Phase | Work | Files | Est. Time | Expected Speedup |
|-------|------|-------|-----------|-----------------|
| 1 | `int.from_bytes` XOR + GF power precompute | `lrc.py`, `fountain.py`, `gf256.py` | <1 hr | 2-5x |
| 2 | NumPy GF mul table + vectorized encode/decode | `gf256.py`, `lrc.py`, `fountain.py` | 1-2 days | 10-50x |
| 3 | Cython `.pyx` for gf256, lrc, fountain | new `.pyx` files, `pyproject.toml` | 2-3 days | 50-100x |
| 4 | CUDA (optional, only if needed) | `cupy` or `numba[cuda]` | 3-5 days | 10-100x (large blocks only) |

**Suggested first step:** Phase 1 (pure Python, zero new deps) gives immediate
benefit with no build changes. Phase 2 (NumPy) builds on existing dependencies
and is the best ROI for the paper — it demonstrates a 10-50x speedup with
minimal new code.
```