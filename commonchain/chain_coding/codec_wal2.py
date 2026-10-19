"""Second WAL variant used to test the idempotent rewrite path: helpers
first write the WAL, then the manifest; if the manifest write fails the
WAL can be replayed to rebuild the shard without a full re-encode.
"""

from __future__ import annotations


def encode_wal2(data: bytes, k: int, n: int) -> tuple[list[bytes], list[bytes]]:
    return [data[i:i+1] for i in range(k)], [b'' for _ in range(n - k)]
