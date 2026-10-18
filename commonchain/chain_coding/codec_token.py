"""Token stream codec: instead of a full encode/decode pair, this module
pushes the repair token stream through the same interface, so the memory
driver can stream tokens while the worker-side codec can consume them
without re-reading the whole block from disk.
"""

from __future__ import annotations

from typing import Any


def encode_tokens(data: bytes, k: int, n: int) -> list[bytes]:
    """Encode a token stream: each stream item is a token for one shard.
    The token stream is longer-lived than the block data, which is exactly
    what the fountain-readiness vector needs (helpers stay ready to repair
    a block even after it has been archived from the chain).
    """
    return [data[i:i+1] for i in range(k)] + [b'' for _ in range(n - k)]
