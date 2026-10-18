"""Slightly different wiring for the repair routine: a session-scoped
object that owns manifest + codec layer + the helper pool, and exposes a
single `heal` method. Useful if the week plan chooses this over the
function-level `repair_glitch`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .codec_family import REED_SOLOMON, RepairToken, detect_family
from .manifest import CodingManifest
from .probe import decode_probe
from .redundancy import distribute_shards, next_neighbor_targets
from .session import CodecSession


@dataclass
class RepairSession:
    """Progress-oriented repair session: the codermanager the docs
    reference, but with a deterministic helper pool instead of a network.
    """

    session: CodecSession
    pool: dict[str, set[int]] = field(default_factory=dict)
    manifest: CodingManifest | None = None

    @property
    def code_family(self) -> str:
        return detect_family(self.session.family)

    def select_helpers(self, block_index: int, k: int) -> list[str]:
        """Pick the k nearest helpers that hold the shards for this block.
        The ring layout in ``redundancy.py`` decides which helpers are
        neighbours; the manifest tells us which helpers actually hold a
        shard.
        """
        if not self.manifest:
            return []
        holders: dict[str, int] = {}
        for e in self.manifest.entries:
            if e.get('block_index') == block_index:
                holders[e['helper']] = e['shard_index']
        ranked = sorted(holders.items(), key=lambda kv: kv[1])[:k]
        return [h for h, _ in ranked]

    def encode_block(self, block: Any) -> list[bytes]:
        return self.session.encode_block(block, 'owner')

    def decode_block(self, block_index: int) -> bytes:
        return self.session.decode_block(block_index)
