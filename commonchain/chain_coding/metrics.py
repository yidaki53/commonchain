"""Coding-layer metrics for the night runs: helper participation,
progressive recovery curves, and checksum validation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryCurve:
    """A single progressive-recovery run: how many helpers participated and
    how much of the block was recovered at each checkpoint.
    """

    block_index: int
    code_family: str
    checkpoints: list[tuple[int, float]]  # (helper_count, progress)

    def to_dict(self) -> dict:
        return {
            'block_index': self.block_index,
            'code_family': self.code_family,
            'checkpoints': [{'helpers': h, 'progress': p} for h, p in self.checkpoints],
        }


def checksum_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
