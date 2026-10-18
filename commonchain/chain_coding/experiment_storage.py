"""Experiment result storage using Polars lazy frames and Parquet.

Provides column-wise, lazy-loading storage for codec experiment results
(finetune sweeps, healing matrices, etc.). Falls back to JSONL if Polars
is not installed.

Design
------
* Results are stored as Parquet files with a stable schema.
* All reads use Polars lazy frames (``scan_parquet``) so column projection
  and predicate pushdown avoid loading unnecessary data.
* Writes append to a partitioned Parquet dataset keyed by experiment name.
* A JSONL mirror is kept for human readability and for environments
  without Polars.

Example
-------
    store = ExperimentStore(path=Path('results/heal_experiments/'))
    store.write_results('finetune', rows)           # rows: list[dict]
    lf = store.scan('finetune')                      # LazyFrame
    df = lf.filter(pl.col('failure_pct') == 50).collect()
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import polars as pl

    _HAS_POLARS = True
except ImportError:
    _HAS_POLARS = False


class ExperimentStore:
    """Column-oriented experiment result storage (Parquet + optional JSONL mirror)."""

    def __init__(self, path: Path | str, jsonl_mirror: bool = True):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.jsonl_mirror = jsonl_mirror

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def write_results(
        self,
        experiment: str,
        rows: list[dict[str, Any]],
    ) -> None:
        """Write ``rows`` to a Parquet dataset for ``experiment``.

        Each row is flattened (one column per key). Nested values are
        JSON-serialized strings. A ``_written_at`` timestamp is added.
        """
        if not rows:
            return

        now = datetime.now(tz=timezone.utc).isoformat()
        flat_rows: list[dict[str, Any]] = []
        for row in rows:
            flat: dict[str, Any] = {"_written_at": now}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    flat[k] = json.dumps(v)
                else:
                    flat[k] = v
            flat_rows.append(flat)

        if _HAS_POLARS:
            df = pl.DataFrame(flat_rows)
            out_path = self.path / f"{experiment}.parquet"
            if out_path.exists():
                existing = pl.read_parquet(out_path)
                df = pl.concat([existing, df], how="diagonal_relaxed")
            df.write_parquet(out_path)
        else:
            # JSONL fallback
            out_path = self.path / f"{experiment}.jsonl"
            with out_path.open("a", encoding="utf-8") as f:
                for row in flat_rows:
                    f.write(json.dumps(row) + "\n")

        if self.jsonl_mirror:
            mirror = self.path / f"{experiment}.jsonl"
            with mirror.open("a", encoding="utf-8") as f:
                for row in flat_rows:
                    f.write(json.dumps(row) + "\n")

    # ------------------------------------------------------------------ #
    # Read (lazy)
    # ------------------------------------------------------------------ #
    def scan(self, experiment: str) -> "pl.LazyFrame | None":
        """Return a Polars LazyFrame for ``experiment`` (lazy, no I/O yet).

        Returns None if Polars is not installed or the file does not exist.
        Column projection and predicate pushdown are applied at collect()
        time, so only needed columns are read from disk.
        """
        if not _HAS_POLARS:
            return None
        out_path = self.path / f"{experiment}.parquet"
        if not out_path.exists():
            return None
        return pl.scan_parquet(out_path)

    def read(self, experiment: str) -> list[dict[str, Any]]:
        """Read all results for ``experiment`` as a list of dicts."""
        if _HAS_POLARS:
            lf = self.scan(experiment)
            if lf is None:
                return []
            return lf.collect().to_dicts()
        # JSONL fallback
        mirror = self.path / f"{experiment}.jsonl"
        if not mirror.exists():
            return []
        rows: list[dict[str, Any]] = []
        with mirror.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    # ------------------------------------------------------------------ #
    # Convenience: filtered column projection
    # ------------------------------------------------------------------ #
    def read_columns(
        self,
        experiment: str,
        columns: list[str],
        filter_expr: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Read only ``columns`` from ``experiment``, optionally filtered.

        Uses Polars predicate pushdown — only matching rows and columns are
        decoded from Parquet.
        """
        if not _HAS_POLARS:
            return self.read(experiment)
        lf = self.scan(experiment)
        if lf is None:
            return []
        lf = lf.select(columns)
        if filter_expr is not None:
            lf = lf.filter(filter_expr)
        return lf.collect().to_dicts()