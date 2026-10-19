"""Progressive repair routine: missing/corrupted blocks are reconstructed
with increasing fidelity as more helpers respond.

The repair routine keeps its aggregation loops out of the hot path. It
records repair tokens in the manifest as the helpers arrive, and the
progress render is pushed to the shared progress path (see
``codec_family.ProgressReport``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .codec_family import detect_family
from .probe import decode_probe
from .session import CodecSession


@dataclass
class RepairResult:
    """Outcome of a heal run."""

    block_index: int
    code_family: str
    recovered: bool
    progress: float
    tokens_received: int
    checksum: str
    error: str = ''


def _xor_block(a: bytes, b: bytes) -> bytes:
    """Simple streaming XOR used to assemble parity shards."""
    return bytes(x ^ y for x, y in zip(a, b))


def repair_glitch(block_index: int, helpers: Iterable[str], session: CodecSession) -> RepairResult:
    """Repair attempt on a single missing/corrupted block. The routine
    asks neighbours for shards, records tokens, and tracks progressive
    reconstruction.

    In this minimal patch the heavy lifting (Vandermonde solve, fountain
    decode, LRC local group) is delegated to the codec layer; this routine
    is the state machine that decides *when* to request, *which* helpers to
    ask, and *how* to combine the tokens.
    """
    code_family = detect_family(session.family)
    tokens: list[tuple[int, bytes]] = []
    manifest = session.manifest
    if not manifest:
        return RepairResult(
            block_index=block_index,
            code_family=code_family,
            recovered=False,
            progress=0.0,
            tokens_received=0,
            checksum='',
            error='no manifest',
        )
    for helper in helpers:
        for e in manifest.entries:
            if e.get('block_index') == block_index and e.get('helper') == helper:
                shard_index = e.get('shard_index', 0)
                shard_bytes = bytes.fromhex(e['shard'])
                tokens.append((shard_index, shard_bytes))
    probe = decode_probe(block_index, session.k, session.n, code_family, tokens)
    return RepairResult(
        block_index=block_index,
        code_family=code_family,
        recovered=probe.progress >= 1.0,
        progress=probe.progress,
        tokens_received=probe.helper_count,
        checksum=probe.checksum,
        error='',
    )
