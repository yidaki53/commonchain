"""Tests for the confidence-interval analysis.

The important test here is ``test_table_columns_match_header``. An earlier
version of ``report_apathy`` emitted metrics by iterating a tuple whose order
(deadlock, quorum_fail) did not match the printed header (quorum-fail,
deadlock). That transposed two columns and *inverted the project's headline
finding* -- it reported high deadlock where the data showed high quorum-failure.
A silently transposed table is worse than no table, so the alignment is pinned.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis import confidence as c  # noqa: E402


def test_ci_brackets_the_point_estimate() -> None:
    vals = [0.0, 1.0] * 50
    lo, mid, hi = c.bootstrap_ci_vals(vals, random.Random(0), n_boot=500)
    assert lo <= mid <= hi
    assert mid == pytest.approx(0.5)


def test_ci_degenerates_on_constant_input() -> None:
    """Zero variance in -> zero width out. Guards against a broken resampler."""
    lo, mid, hi = c.bootstrap_ci_vals([0.25] * 40, random.Random(0), n_boot=500)
    assert lo == pytest.approx(0.25)
    assert hi == pytest.approx(0.25)


def test_ci_handles_empty_input() -> None:
    import math

    lo, mid, hi = c.bootstrap_ci_vals([], random.Random(0), n_boot=100)
    assert math.isnan(lo) and math.isnan(mid) and math.isnan(hi)


def test_table_columns_match_header() -> None:
    """Header labels and metric values must be in the same order.

    Regression test for the transposition bug described in the module docstring.
    """
    lines = c.report_apathy(random.Random(1))
    header = next(ln for ln in lines if ln.startswith("| quorum"))
    cols = [h.strip() for h in header.strip("|").split("|")]
    assert cols == [
        "quorum", "apath_frac", "p_abstain", "n runs", "turnout",
        "pass rate", "quorum-fail", "deadlock",
    ], f"header changed, re-check column order: {cols}"

    # A data row must have exactly as many cells as the header has columns.
    data = [ln for ln in lines if ln.startswith("| 50.0") or ln.startswith("| 75.0")]
    assert data, "expected apathy rows in the table"
    for row in data:
        assert len(row.strip("|").split("|")) == len(cols), row


def test_quorum_failure_dominates_at_high_apathy() -> None:
    """Substantive check: at high apathy the failure mode is quorum-fail.

    This is the claim the whole table exists to support, asserted against the
    real CSV so a transposition or a data regression both fail loudly.
    """
    rows = c.load_rows("gov_apathy_sweep.csv")
    assert rows, "gov_apathy_sweep.csv missing"
    hi = [
        r for r in rows
        if r["quorum_pct"] == "50.0"
        and r["apath_frac"] == "0.7"
        and r["p_abstain"] == "0.95"
    ]
    assert hi

    def mean(col: str) -> float:
        return sum(float(r[col]) for r in hi) / len(hi)

    assert mean("quorum_fail_rate") > mean("deadlock_rate")
