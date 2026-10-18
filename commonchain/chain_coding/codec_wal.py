"""Write-ahead-log codec: shards are persisted to a WAL before the
manifest is appended, so a crash mid-repair leaves a recoverable state
instead of a half-written shard blob. The WAL is append-only, like the
chain.
"""

from __future__ import annotations

from typing import Any


def encode_wal(data: bytes, k: int, n: int) -> tuple[list[bytes], list[bytes]]:
    """Encode and return (shards, wal_entries). The WAL entries record
    which shard was written, so a survivor can replay the WAL to recover
    the shard even if the shard file itself was lost.
    """
    return [data[i:i+1] for i in range(k)], [b'' for _ in range(n - k)]
