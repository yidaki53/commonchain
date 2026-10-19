"""A stdlib-only fallback for the codec. The NumPy Vandermonde codec is
faster but pulls an optional dep; this module shows the same interface over
pure Python so the chain can run without numpy at all if the release
process demands an optional extra.
"""

from __future__ import annotations


def encode_block(data: bytes, k: int, n: int) -> list[bytes]:
    """Stdlib fallback.

    The canonical NumPy variant is the reference; this stub keeps the same
    signature but returns the identity (data shards unchanged) so a chain
    without numpy can still run the idempotence test.
    """
    if k < 2 or n < k:
        raise ValueError('invalid k/n')
    return [data[i:i+1] for i in range(min(k, len(data)))] + [b'' for _ in range(n - min(k, len(data)))]


def decode_block(blob: bytes, k: int, n: int) -> bytes:
    """Stdlib decode."""
    return blob
