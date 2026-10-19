"""Rateless Fountain (LT) code over byte strings.

A fountain code can produce an unlimited number of encoded shards from k
source shards. Each encoded shard is the XOR of a random subset of the
source blocks, where the subset size (degree) is drawn from the ideal
soliton distribution. Decoding uses a peeling (belief-propagation)
decoder: find an encoded shard of degree 1, recover its source block,
XOR it into all shards containing that source, and repeat.

With k encoded shards, recovery succeeds with moderate probability; with
k + O(sqrt(k) * log(k)) shards, recovery succeeds with high probability.
This makes fountain codes progressive: more helpers = better estimate.

Performance notes
-----------------
* XOR of source shards uses ``int.from_bytes`` / ``int.to_bytes`` for
  blocks >= 64 bytes (Tier 1, ~5-10x faster than byte loops).
"""

from __future__ import annotations

import random


def _ideal_soliton_distribution(k: int) -> list[float]:
    probs: list[float] = [0.0] * (k + 1)
    probs[1] = 1.0 / k
    for d in range(2, k + 1):
        probs[d] = 1.0 / (d * (d - 1))
    total = sum(probs)
    if total > 0:
        probs = [p / total for p in probs]
    return probs


def _sample_degree(k: int, rng: random.Random) -> int:
    probs = _ideal_soliton_distribution(k)
    r = rng.random()
    cum = 0.0
    for d in range(1, k + 1):
        cum += probs[d]
        if r < cum:
            return d
    return k


def fountain_encode_shards(
    data_shards: list[bytes],
    n: int,
    k: int,
    seed: int | None = None,
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

    base_seed = seed if seed is not None else 42
    shards: list[bytearray] = [bytearray(length) for _ in range(n)]

    for j in range(n):
        # Per-shard rng: the decoder replays choices with
        # Random(base_seed + j), so encoding must derive them the same way.
        rng = random.Random(base_seed + j)
        d = _sample_degree(k, rng)
        source_indices = rng.sample(range(k), d)
        # Tier 1: int.from_bytes XOR for blocks >= 64 bytes.
        if length >= 64:
            acc = 0
            for idx in source_indices:
                acc ^= int.from_bytes(data_shards[idx], "big")
            out = acc.to_bytes(length, "big")
        else:
            out = bytearray(length)
            for idx in source_indices:
                src = data_shards[idx]
                for b in range(length):
                    out[b] ^= src[b]
        shards[j] = out

    return [bytes(s) for s in shards]


def fountain_decode_from_available(
    available: dict[int, bytes],
    k: int,
    n: int,
    seed: int | None = None,
) -> tuple[list[bytes], float]:
    if len(available) == 0:
        length = len(next(iter(available.values()))) if available else 0
        return [b"\x00" * length] * k, 0.0

    any_shard = next(iter(available.values()))
    length = len(any_shard)
    base_seed = seed if seed is not None else 42

    # Reconstruct the encoding choices for each available shard index.
    # We replay the same random sequence used during encoding: for shard
    # index j, we create a Random(seed + j) and sample degree then sources.
    shard_degrees: dict[int, int] = {}
    shard_sources: dict[int, list[int]] = {}
    for j in sorted(available.keys()):
        rng_for_j = random.Random(base_seed + j)
        d = _sample_degree(k, rng_for_j)
        source_indices = rng_for_j.sample(range(k), d)
        shard_degrees[j] = d
        shard_sources[j] = source_indices

    # Peeling decoder
    remaining_source = [True] * k
    recovered: list[bytearray | None] = [None] * k
    recovered_count = 0

    remaining: dict[int, bytearray] = {j: bytearray(available[j]) for j in available}
    remaining_degrees = dict(shard_degrees)

    changed = True
    while changed:
        changed = False
        for j in list(remaining.keys()):
            if remaining_degrees[j] == 1:
                sources = shard_sources[j]
                unrecovered = [s for s in sources if remaining_source[s]]
                if len(unrecovered) == 1:
                    source_idx = unrecovered[0]
                    recovered[source_idx] = bytearray(remaining[j])
                    remaining_source[source_idx] = False
                    recovered_count += 1
                    changed = True

                    src_bytes = recovered[source_idx]
                    for j2 in list(remaining.keys()):
                        if j2 == j:
                            continue
                        if source_idx in shard_sources[j2]:
                            sb = remaining[j2]
                            # Tier 1: int.from_bytes XOR for blocks >= 64 bytes.
                            if length >= 64:
                                acc = int.from_bytes(sb, "big") ^ int.from_bytes(src_bytes, "big")
                                remaining[j2] = acc.to_bytes(length, "big")
                            else:
                                for b in range(length):
                                    sb[b] ^= src_bytes[b]
                            remaining_degrees[j2] -= 1

                    del remaining[j]
                    del remaining_degrees[j]

    progress = recovered_count / k
    source_shards = [
        bytes(r) if r is not None else b"\x00" * length for r in recovered
    ]
    return source_shards, progress
