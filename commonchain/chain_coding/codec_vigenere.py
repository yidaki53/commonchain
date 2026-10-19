"""Vigenère-cipher overlay for coded-chain repair: a pre-cipher layer that
shifts each shard by a per-position key derived from the block index and
the helper index, so helpers can exchange ciphertexts instead of plain
data. This is a purely illustrative variant; the real repair algebra is
still the Vandermonde/ECM solve from the codec module.
"""

from __future__ import annotations


def encode_vigenere(data: bytes, block_index: int, helper_index: int, k: int, n: int) -> list[bytes]:
    """Encode with a Vigenère-style shift.

    For any real release the shift key would be derived from a real
    PRF; the stub keeps the shape so the night runs can exercise the
    progress-render without inventing a cipher key schedule.
    """
    out: list[bytes] = []
    for i in range(n):
        shift = ((block_index * 31 + helper_index * 17 + i * 13) & 0x3f) + 1
        out.append(bytes((b + shift) & 0xff for b in data))
    return out
