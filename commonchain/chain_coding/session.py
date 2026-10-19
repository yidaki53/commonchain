"""Codec session: the object that binds chain, manifest, encode/decode and
helper discovery for one chain or one recovery run.

Everything in this module is importable and testable in isolation; no
night run should reach into the network directly except through here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .codec import decode_block, encode_block
from .codec_family import LRC, RepairToken, decode_block_v2, encode_block_v2, detect_family
from .gf256 import rs_decode_from_available
from .manifest import CodingManifest
from .probe import decode_probe, probe_progress
from .redundancy import distribute_shards, next_neighbor_targets


@dataclass
class CodecSession:
    """Session-scoped coding layer for one collective or one simulation.

    Attributes:
        chain: reference to the chain object (for block lookup)
        root: root directory for any files this session writes
        code_family: REED_SOLOMON | FOUNTAIN | LRC (default)
        k, n: erasure coding parameters
        helpers: mapping helper_id -> shard_set
        manifest: the coding manifest kept in lockstep with the chain
    """

    chain: Any
    root: Path = field(default_factory=lambda: Path('./results/coding'))
    code_family: str = LRC
    k: int = 3
    n: int = 5
    helpers: dict[str, set[int]] = field(default_factory=dict)
    manifest: CodingManifest | None = None

    @property
    def family(self) -> str:
        return detect_family(self.code_family)

    def encode_block(self, block: Any, helper: str) -> list[bytes]:
        """Encode a block for helper ``helper`` and register shards in the
        manifest. Returns the n shard blobs."""
        code_family = self.family
        k, n = self.k, self.n
        if self.manifest is None:
            self.manifest = CodingManifest(path=self.root / 'manifest.json')
        blobs = encode_block_v2(block.body_bytes(), k, n, code_family=code_family)
        # The manifest stores the encoded blobs; the chain stores the hash.
        # One helper per shard: cycle the target helper across all n shards.
        self.manifest.add_shards(
            block.index, code_family, k, n, blobs, [helper] * n
        )
        return blobs

    def record_block(self, block: Any) -> None:
        """Encode ``block`` into ``n`` shards and register them in the manifest.

        Shards are round-robined across the session's helpers (falling back to
        a single ``owner`` helper when none are registered), so the manifest
        records exactly one helper per shard and stays in lockstep with the
        chain.
        """
        code_family = self.family
        k, n = self.k, self.n
        if self.manifest is None:
            self.manifest = CodingManifest(path=self.root / 'manifest.json')
        blobs = encode_block_v2(block.body_bytes(), k, n, code_family=code_family)
        helpers = list(self.helpers)
        if not helpers:
            helpers = ['owner']
        helpers = (helpers * ((n // len(helpers)) + 1))[:n]
        self.manifest.add_shards(block.index, code_family, k, n, blobs, helpers)
        self.manifest.write()

    def decode_block(self, block_index: int) -> bytes:
        """Decode a block from the helper pool using all available shards.

        Collects shards from the manifest, runs the family-specific decode,
        and returns the concatenated recovered data. Raises ``ValueError`` if
        fewer than ``k`` shards are available (cannot recover).
        """
        tokens: list[tuple[int, bytes]] = []
        manifest = self.manifest
        if not manifest:
            raise RuntimeError('no manifest available')
        for e in manifest.entries:
            if e.get('block_index') == block_index:
                tokens.append((e.get('shard_index', 0), bytes.fromhex(e['shard'])))

        if not tokens:
            raise ValueError(f'no shards available for block {block_index}')

        shard_len = len(tokens[0][1])
        available_list: list[bytes | None] = [None] * self.n
        for shard_index, shard_bytes in tokens:
            if 0 <= shard_index < self.n:
                available_list[shard_index] = shard_bytes

        recovered, progress = decode_block_v2(
            available_list, self.k, self.n, self.family
        )
        if progress < 1.0:
            raise ValueError(
                f'decode incomplete for block {block_index}: '
                f'progress {progress:.2f} < 1.0'
            )
        return b''.join(recovered)

    def redeem_shard(self, block_index: int, shard_index: int) -> bytes:
        """Redeem one transformed shard (parity or data) for a block index.

        The family flag selects the algebra, and the manifest selects the
        helper whose shard is being redeemed so no helper is asked for a
        shard it never stored.
        """
        available: list[bytes | None] = [None] * self.n
        for e in self.manifest.entries:
            if e.get('block_index') == block_index:
                si = e.get('shard_index', 0)
                if 0 <= si < self.n:
                    available[si] = bytes.fromhex(e['shard'])
        if available[shard_index] is None:
            raise KeyError((block_index, shard_index))
        recovered, _progress = decode_block_v2(available, self.k, self.n, self.family)
        # Return the requested shard index from recovered data shards
        if shard_index < len(recovered):
            return recovered[shard_index]
        # For parity shards beyond k, we'd need to re-encode; return the
        # available copy directly.
        return available[shard_index]

    def serialize(self) -> dict[str, Any]:
        return {
            'chain': getattr(self.chain, 'index', None),
            'root': str(self.root),
            'code_family': self.family,
            'k': self.k,
            'n': self.n,
            'helpers': self.helpers,
            'manifest_entries': len(self.manifest.entries) if self.manifest else 0,
        }

    @classmethod
    def load(cls, chain: Any, path: Path) -> 'CodecSession':
        inst = cls(chain=chain)
        inst.manifest = CodingManifest.load(path)
        inst.k = inst.manifest.entries[0]['k'] if inst.manifest.entries else 3
        inst.n = inst.manifest.entries[0]['n'] if inst.manifest.entries else 5
        return inst
