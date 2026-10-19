"""Redundancy placement for helper-to-helper repair.

The encoding scheme is a deterministic ring: shard i goes to helper
``(i % m)``, and the ring order tells a helper which physical neighbours
to ask when it is missing a piece. This preserves the progressive
reconstruction property from the task notes while keeping the manifest
small enough for night-5 grid runs.
"""

from __future__ import annotations


def ring_positions(n_shards: int, m: int) -> list[int]:
    """Ring position of each shard when the helpers are arranged in a ring
    of size m. Position 0 is the 'owner' of the first shard."""
    return [(i * m) % n_shards for i in range(m)]


def ring_neighbors(shard_index: int, m: int) -> list[int]:
    """Physical neighbours of the helper holding shard ``shard_index``,
    clockwise, starting with the next helper."""
    return [(shard_index + j) % m for j in range(1, m)]


def next_neighbor_targets(shard_index: int, m: int, k: int) -> list[int]:
    """The k nearest helper IDs around the ring that hold the k data
    shards for a block with n=k+1 shards; used to locate the parity shard
    for a missing block."""
    if k < 2:
        raise ValueError('k must be >= 2')
    if n_shards := k + 1:
        return [(shard_index + j) % n_shards for j in range(1, k + 1)]
    raise ValueError('n must be at least k+1')


def distribute_shards(n_shards: int, m: int, k: int = 1) -> dict[int, list[int]]:
    """Map each block shard to the helpers that hold a copy for redundancy.

    The result is a dict shard_index -> helper_list. The layout is a
    simple round-robin with the owner first.
    """
    if m < 1:
        raise ValueError('m must be >= 1')
    positions = ring_positions(n_shards, m)
    if n_shards % m != 0:
        raise ValueError('ring layout requires n_shards to be a multiple of m')
    out: dict[int, list[int]] = {i: [] for i in range(n_shards)}
    for shard, helper in enumerate(range(m)):
        out[positions[shard]].append(helper)
    return out
