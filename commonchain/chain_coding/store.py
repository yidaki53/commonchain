"""File-based helper store for encoded shards and repair tokens.

Each helper keeps a directory of blobs: one per block index, plus a
fountain-readiness map that stores the repair tokens other helpers can
exchange. The codec layer never calls the network; the session does that,
and the store is only the reliable local cache of what a helper already
holds.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .codec import encode_block, decode_block
from .codec_family import RepairToken, ProgressReport


@dataclass
class HelperStore:
    """Local store for one helper's coded view of the chain.

    The filename is a hash of (block_index, shard_index) so shards are
    never silently overwritten by a later, conflicting version of the same
    index; the sidecar token file records what other helpers can use to
    repair this helper's own missing blocks.
    """

    root: Path = field(default_factory=lambda: Path('./results/helper_store'))
    tokens: dict[tuple[int, int], bytes] = field(default_factory=dict)

    def add_shard(self, block_index: int, shard_index: int, blob: bytes) -> None:
        blob_hash = hashlib.sha256(blob).hexdigest()
        out = self.root / f'block_{block_index}' / f'shard_{shard_index}_{blob_hash}.bin'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        self.tokens[(block_index, shard_index)] = blob

    def get_shard(self, block_index: int, shard_index: int) -> bytes:
        candidates = list(self.root.glob(f'block_{block_index}/shard_{shard_index}_*.bin'))
        if not candidates:
            raise KeyError((block_index, shard_index))
        return candidates[0].read_bytes()

    def record_token(self, block_index: int, shard_index: int, token: bytes) -> None:
        self.tokens[(block_index, shard_index)] = token
        (self.root / f'token_{block_index}_{shard_index}.bin').write_bytes(token)

    def encode(self, data: bytes, k: int, n: int) -> list[bytes]:
        return encode_block(data, k, n)

    def decode(self, data: bytes, k: int, n: int) -> bytes:
        return decode_block(data, k, n)
