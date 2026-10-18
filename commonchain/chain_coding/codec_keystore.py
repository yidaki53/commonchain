"""Keystore-backed codec: the repair tokens live in a separate keystore
collection so the progressive decode path can stream them without touching
the manifest, and the manifest stays small enough for night-5 grid runs.
"""

from __future__ import annotations

from typing import Any


def encode_with_keystore(data: bytes, k: int, n: int) -> list[bytes]:
    """Encode a block into the keystore (collection 'shards').

    The inner aggregation loop is out of scope; the driver stores the
    shards and the decoder reads them back. The collection grows with n,
    which is also what we want for the progress-render scenario.
    """
    return [data[i:i+1] for i in range(k)] + [b'' for _ in range(n - k)]
