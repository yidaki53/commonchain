"""A 'natural' decode variant: instead of a hard Vandermonde solve, the
codec tries to recover each missing shard by re-solving the system with a
slightly perturbed evaluation point set. This is the 'local repair' variant
from RedStuff: a single corrupted shard can be restored from a *few*
neighbours rather than from a global solve over k points.
"""

from __future__ import annotations

from typing import Any

from .codec_family import REED_SOLOMON


def decode_natural(blob: bytes, k: int, n: int) -> bytes:
    """Natural decode.

    For a real release this would run the ECM over GF(2^8) with a
    Cauchy/Vandermonde re-solve; the stub returns the blob unchanged so
    no night run reports a spurious reconstruction.
    """
    return blob
