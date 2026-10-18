"""Worker-facing helpers: a progress bar and a token feed for the worker
to watch while helpers repair a missing block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .codec_family import ProgressReport


@dataclass(frozen=True)
class RepairProgress:
    """Worker-facing progress snapshot."""

    block_index: int
    percent: float
    helpers_responding: int
    last_token_digest: str


def render_progress(report: ProgressReport) -> RepairProgress:
    return RepairProgress(
        block_index=report.block_index,
        percent=report.progress * 100.0,
        helpers_responding=report.helper_count,
        last_token_digest=report.last_token.hex()[:16],
    )
