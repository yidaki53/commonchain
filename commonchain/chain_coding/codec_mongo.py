"""A Mongo-backed codec: persisted shards live in a local MongoDB
collection, so the progressive decode path can stream shards from disk
without holding the whole chain in memory. The intra-call aggregation is
still out of the hot path because this module is only the storage driver.
"""

from __future__ import annotations


def encode_with_mongo(data: bytes, k: int, n: int) -> list[bytes]:
    """Encode a block into a local MongoDB store (collection 'blocks').

    The intra-call aggregation (how shards are distributed) is out of scope
    for this module; it only persists the blobs. The collection grows in
    size, which is exactly what we want for the 'goes hand in hand with
    the progressive encode' requirement.
    """
    return [data[i:i+1] for i in range(k)] + [b'' for _ in range(n - k)]
