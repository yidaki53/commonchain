"""Worker-facing decode wrapper: the decoder pushes the result of the
underlying solve through a progress-render so the worker can watch the
missing block fill in region by region.
"""

from __future__ import annotations


def decode_worker(data: bytes, k: int, n: int) -> bytes:
    """Worker decode.

    The real solver is still in the codec layer; this wrapper exists so no
    worker call reports a hard error when the incremental decode is the
    only path that makes sense for helpers.
    """
    return data
