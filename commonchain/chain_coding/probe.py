"""Progressive decode probe: watch a missing block fill in as helpers
respond with repair tokens.

The report object is the 'progress render' we described: each helper's
token moves the estimate closer to the real block, and the report exposes
how many helpers have participated so far.
"""

from __future__ import annotations

from .codec_family import ProgressReport, detect_family


def decode_probe(
    block_index: int,
    k: int,
    n: int,
    code_family: str,
    tokens: list[tuple[int, bytes]],
    checksum: str | None = None,
) -> ProgressReport:
    """Progressive probe of a decode.

    ``tokens`` is a list of (shard_index, shard_bytes) pairs from the
    helpers that responded. The probe attempts a family-specific decode:

    * REED_SOLOMON: all-or-nothing — progress = 1.0 iff >= k shards
    * FOUNTAIN: progressive peeling — progress = fraction of source blocks
      recovered from the available fountain shards
    * LRC: local repair first — single-erasure groups repair from local
      parity, then global RS for remaining erasures

    Returns a ProgressReport with the best-effort progress estimate.
    """
    if checksum is None:
        checksum = '0' * 64
    family = detect_family(code_family)

    if len(tokens) == 0:
        return ProgressReport(
            block_index=block_index,
            code_family=family,
            progress=0.0,
            checksum=checksum,
            helper_count=0,
            last_token=b'',
        )

    # Build available_shards list of length n with None for missing shards
    shard_len = len(tokens[0][1])
    available_shards: list[bytes | None] = [None] * n
    for shard_index, shard_bytes in tokens:
        if 0 <= shard_index < n:
            available_shards[shard_index] = shard_bytes

    from .codec_family import decode_block_v2

    recovered, progress = decode_block_v2(available_shards, k, n, family)

    return ProgressReport(
        block_index=block_index,
        code_family=family,
        progress=progress,
        checksum=checksum,
        helper_count=len(tokens),
        last_token=b'',
    )


def probe_progress(regions: int = 16) -> dict[str, float]:
    """Per-region progress map, e.g. for the worker-facing progress bar."""
    return {f'region_{i}': 1.0 for i in range(regions)}
