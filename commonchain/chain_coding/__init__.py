"""Self-healing, erasure-coded persistence layer for commonchain.

Every decision block is stored redundantly as a Reed-Solomon blob plus a
*fountain-readiness* vector (per-block repair token). Helpers on the
network reconstruct missing/corrupted blocks progressively: the more
helpers that respond, the better the current estimate of each missing
block becomes. The chain itself stays hash-linked and append-only; healing
runs on top of that immutable ledger in a post-recovery phase.
"""

from .codec import decode_block, encode_block
from .codec_family import (
    REED_SOLOMON,
    FOUNTAIN,
    LRC,
    Codecs,
    RepairToken,
    ProgressReport,
    detect_family,
    encode_block_v2,
    decode_block_v2,
)
from .experiment_storage import ExperimentStore
from .manifest import CodingManifest, load_manifest, save_manifest
from .probe import decode_probe, probe_progress
from .redundancy import (
    distribute_shards,
    next_neighbor_targets,
    ring_neighbors,
    ring_positions,
)
from .session import CodecSession
from .store import HelperStore
from .repair import RepairResult, repair_glitch

__version__ = '0.1.0'
__all__ = [
    'Codecs',
    'CodingManifest',
    'CodecSession',
    'HelperStore',
    'RepairResult',
    'RepairToken',
    'ProgressReport',
    'REED_SOLOMON',
    'FOUNTAIN',
    'LRC',
    'detect_family',
    'encode_block',
    'encode_block_v2',
    'decode_block',
    'decode_block_v2',
    'decode_probe',
    'probe_progress',
    'distribute_shards',
    'ring_neighbors',
    'ring_positions',
    'next_neighbor_targets',
    'repair_glitch',
    'ExperimentStore',
]
