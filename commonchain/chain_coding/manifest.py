"""Persistence manifest for encoded blocks.

The manifest records, per block index, the code family, k, n, the shard
indices on each helper, and the helper identity that wrote each shard. It is
append-only (like the chain) and is the handshake document every helper
reads before it answers a repair request.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .codec_family import CODECS, RepairToken, detect_family
from .probe import decode_probe


def load_manifest(path: Path) -> CodingManifest:
    """Load a manifest from disk and return it."""
    return CodingManifest.load(path)


def save_manifest(manifest: CodingManifest, path: Path | None = None) -> None:
    """Write a manifest to disk (or to the manifest's own path)."""
    return manifest.write(path)



@dataclass
class BlockShard:
    """One shard written to one helper."""

    block_index: int
    code_family: str
    k: int
    n: int
    shard_index: int
    helper: str
    shard: bytes
    checksum: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.shard).hexdigest()


@dataclass
class CodingManifest:
    """Append-only record of how a block was encoded and spread across
    helpers.

    The chain itself stays hash-linked; this manifest is the *coding*
    ledger that the helpers consult during progressive repair.
    """

    path: Path
    version: int = 1
    entries: list[dict] = field(default_factory=list)

    def add_entry(self, entry: dict) -> None:
        self.entries.append(entry)

    def add_shards(self, block_index: int, code_family: str, k: int, n: int, shards: list[bytes], helpers: Iterable[str]) -> None:
        if len(shards) != n or len(list(helpers)) != n:
            raise ValueError('shard count must match manifest n')
        for i, (shard, helper) in enumerate(zip(shards, helpers)):
            self.add_entry({
                'block_index': block_index,
                'code_family': code_family,
                'k': k,
                'n': n,
                'shard_index': i,
                'helper': helper,
                'shard': shard.hex(),
                'checksum': hashlib.sha256(shard).hexdigest(),
            })

    def write(self, path: Path | None = None) -> None:
        path = Path(path) if path is not None else self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.model_dump(), indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path: Path) -> 'CodingManifest':
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        inst = cls(path=path)
        inst.entries = data.get('entries', [])
        return inst

    def model_dump(self) -> dict[str, Any]:
        return {'version': self.version, 'entries': self.entries}
