"""Locally Repairable Codes (LRC) over byte strings.

LRC partitions k data shards into small local groups. Each group gets a
local parity shard (XOR of group members). A single erasure within a
group can be repaired from just the other group members plus the local
parity — far fewer helpers than a global Reed-Solomon solve. Additional
global parity shards provide protection against multiple simultaneous
erasures.

Layout (n total shards):
  - k data shards (indices 0..k-1); these are the raw polynomial
    coefficients c_0..c_{k-1} of the RS code used for global parity
  - gpc local parity shards (indices k..k+gpc-1), one per group
  - r global RS parity shards (indices k+gpc..n-1), r = n - k - gpc;
    shard k+gpc+p holds the RS evaluation of the data polynomial at
    xi = k+p+1 (so an RS code of length k+r is embedded at those
    evaluation points)

A single missing data shard in a group of size L needs only L helpers
(the other L-1 data shards + local parity). Multiple missing shards
fall back to a global solve that mixes the surviving raw coefficients
with the global RS parity evaluations (rs_solve_partial).

The number of local groups adapts to n so that exactly n shards are
always emitted (when n is too small to give every group a parity, groups
merge; when n == k there is no parity at all).

Performance notes
-----------------
* Local parity XOR uses ``int.from_bytes`` / ``int.to_bytes`` for blocks
  >= 64 bytes (Tier 1, ~5-10x faster than byte loops).
* For blocks >= CUDA_THRESHOLD bytes (imported from gf256), NumPy/CuPy
  vectorized XOR is used (Tier 2/4).
"""

from __future__ import annotations

from .gf256 import CUDA_THRESHOLD, rs_encode_shards, rs_solve_partial


def _group_size(k: int) -> int:
    """Default group size derived from k (used when group_size is not overridden)."""
    if k <= 4:
        return 2
    if k <= 8:
        return 3
    return 4


def _layout(
    k: int,
    n: int,
    group_size: int | None = None,
) -> tuple[list[list[int]], int]:
    """Return (groups, local_parity_count) for a feasible (k, n) layout.

    ``groups`` is the list of data-shard index lists, one per local
    parity group. The group count is capped at n - k so exactly n shards
    are emitted (data + one local parity per group + global RS parity).

    If ``group_size`` is given, it overrides the default derived from k.
    """
    if k < 2:
        raise ValueError("k must be >= 2")
    if n < k:
        raise ValueError("n must be >= k")
    g = group_size if group_size is not None else _group_size(k)
    if g < 1:
        g = 1
    num_groups = (k + g - 1) // g
    max_groups = n - k  # room left for local parities after the data shards
    if num_groups > max_groups:
        num_groups = max(0, max_groups)
    if num_groups == 0:
        return [list(range(k))], 0
    # Split k items into num_groups groups as evenly as possible.
    base = k // num_groups
    extra = k % num_groups
    groups: list[list[int]] = []
    idx = 0
    for gi in range(num_groups):
        size = base + (1 if gi < extra else 0)
        groups.append(list(range(idx, idx + size)))
        idx += size
    return groups, num_groups


def lrc_encode_shards(
    data_shards: list[bytes],
    n: int,
    k: int,
    group_size: int | None = None,
) -> list[bytes]:
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

    groups, local_parity_count = _layout(k, n, group_size=group_size)
    global_parity_count = n - k - local_parity_count

    shards: list[bytearray] = [bytearray(s) for s in data_shards]

    # Local parity: XOR of group members.
    # Use int.from_bytes XOR for blocks >= 64 bytes (Tier 1),
    # NumPy vectorized XOR for blocks >= CUDA_THRESHOLD (Tier 2/4).
    if length >= CUDA_THRESHOLD:
        import numpy as np

        data_arr = np.frombuffer(b"".join(data_shards), dtype=np.uint8).reshape(k, length)
        for group in groups:
            local_parity = np.bitwise_xor.reduce(data_arr[list(group)])
            shards.append(bytearray(local_parity.tobytes()))
    else:
        for group in groups:
            acc = 0
            for j in group:
                acc ^= int.from_bytes(data_shards[j], "big")
            local_parity = acc.to_bytes(length, "big")
            shards.append(bytearray(local_parity))

    if global_parity_count > 0:
        rs_parity = rs_encode_shards(data_shards, k + global_parity_count, k)
        for p in range(global_parity_count):
            shards.append(bytearray(rs_parity[k + p]))

    return [bytes(s) for s in shards]


def lrc_decode_from_available(
    available: dict[int, bytes],
    k: int,
    n: int,
    group_size: int | None = None,
) -> tuple[list[bytes], float]:
    if len(available) == 0:
        return [b""] * k, 0.0

    length = len(next(iter(available.values())))
    groups, local_parity_count = _layout(k, n, group_size=group_size)
    global_parity_count = n - k - local_parity_count

    have_data = [False] * k
    recovered: list[bytearray | None] = [None] * k

    for idx in range(k):
        if idx in available:
            recovered[idx] = bytearray(available[idx])
            have_data[idx] = True

    for group_idx, group in enumerate(groups):
        local_parity_idx = k + group_idx

        missing_in_group = [i for i in group if not have_data[i]]
        if len(missing_in_group) == 1 and local_parity_idx in available:
            missing_idx = missing_in_group[0]
            other_indices = [i for i in group if i != missing_idx]
            # Tier 1: int.from_bytes XOR for local repair (>= 64 bytes).
            if length >= 64:
                acc = int.from_bytes(available[local_parity_idx], "big")
                for i in other_indices:
                    if have_data[i]:
                        acc ^= int.from_bytes(recovered[i], "big")
                repair = acc.to_bytes(length, "big")
            else:
                repair = bytearray(available[local_parity_idx])
                for i in other_indices:
                    if have_data[i]:
                        src = recovered[i]
                        for b in range(length):
                            repair[b] ^= src[b]
            recovered[missing_idx] = bytearray(repair)
            have_data[missing_idx] = True

    missing_count = sum(1 for h in have_data if not h)
    if missing_count > 0 and global_parity_count > 0:
        # Global fallback: surviving data shards are raw polynomial
        # coefficients; global parity shards are RS evaluations at
        # xi = k+p+1. Local parity shards (k..k+local_parity_count-1)
        # are XORs of group members, so they are neither and are excluded.
        known_coeffs: dict[int, bytes] = {}
        for idx in range(k):
            if have_data[idx] and recovered[idx] is not None:
                known_coeffs[idx] = bytes(recovered[idx])
        evals: dict[int, bytes] = {}
        global_parity_start = k + local_parity_count
        for p in range(global_parity_count):
            idx = global_parity_start + p
            if idx in available:
                evals[k + p + 1] = available[idx]

        if len(evals) >= missing_count:
            try:
                rs_data = rs_solve_partial(known_coeffs, evals, k)
                for i in range(k):
                    if not have_data[i]:
                        recovered[i] = bytearray(rs_data[i])
                        have_data[i] = True
            except ValueError:
                pass

    progress = sum(1 for h in have_data if h) / k
    data_shards = [
        bytes(r) if r is not None else b"\x00" * length for r in recovered
    ]
    return data_shards, progress