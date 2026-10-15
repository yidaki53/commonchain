"""Cluster-bootstrap confidence intervals over the night-1 sweep CSVs.

Why cluster at the seed
-----------------------
Each sweep row is one *run* of ``n_proposals`` correlated decisions sharing a
single RNG stream. Treating those proposals as independent observations would
understate the interval by roughly sqrt(n_proposals) and manufacture precision
that is not there. So we resample **runs** (seeds) with replacement and compute
the statistic on each resample. That is the honest unit of variation.

Every quorum claim is reported alongside ``mean_turnout``: a flat
``quorum_fail_rate`` is indistinguishable from a quorum that was never in reach
unless turnout is visible next to it.
"""

from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT = RESULTS / "night2"
N_BOOT = 10_000
ALPHA = 0.05

# Columns that carry a rate metric. NOTE: this ordering lists deadlock before
# quorum_fail, which does NOT match the printed table order. Callers must name
# their columns explicitly rather than iterating this tuple -- see report_apathy
# and tests/test_confidence.py, which pins the header/column alignment.
METRICS = ("pass_rate", "deadlock_rate", "quorum_fail_rate", "adversarial_win_rate")


def _mean_vals(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def load_rows(name: str) -> list[dict]:
    path = RESULTS / name
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open()))
    # Sweep rows mark failed cells with -1 sentinels; exclude them.
    return [
        r for r in rows
        if r.get("pass_rate") not in (None, "", "-1")
    ]


def _numeric(rows: list[dict], col: str) -> list[float]:
    """Parse a metric column once. Resampling then reuses these floats.

    Re-parsing strings inside the bootstrap loop is what makes naive
    implementations ~50x slower than they need to be: the conversion cost is
    paid on every resample instead of once per group.
    """
    out = []
    for r in rows:
        v = r.get(col)
        if v in (None, "", "-1"):
            continue
        try:
            out.append(float(v))
        except ValueError:
            continue
    return out


def _mean_vals(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def bootstrap_ci_vals(
    vals: list[float], rng: random.Random, n_boot: int = N_BOOT
) -> tuple[float, float, float]:
    """Percentile bootstrap over pre-parsed values. Returns (lo, mid, hi).

    Implementation note: the inner resample is generated in bulk rather than
    with a Python-level loop of ``randrange`` calls. A per-cell cost of
    n_boot * n draws is ~5.6M RNG calls at the grid's largest cell, which is
    ~30s in pure Python -- tolerable once, but not across a whole sweep.
    """
    n = len(vals)
    if n == 0:
        return (float("nan"),) * 3
    choices = rng.choices
    stats = [
        math.fsum(choices(vals, k=n)) / n
        for _ in range(n_boot)
    ]
    stats.sort()
    lo = stats[int((ALPHA / 2) * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - ALPHA / 2) * n_boot))]
    return lo, _mean_vals(vals), hi


def group_by(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        out[tuple(r[k] for k in keys)].append(r)
    return out


def fmt(x: float) -> str:
    return "n/a" if math.isnan(x) else f"{x:.3f}"


def report_apathy(rng: random.Random) -> list[str]:
    """Table 1: quorum x apathy, with CIs and turnout."""
    rows = load_rows("gov_apathy_sweep.csv")
    lines = [
        "# Table 1: Quorum pathologies with cluster-bootstrap 95% CIs",
        "",
        f"Source: `gov_apathy_sweep.csv`, {len(rows)} runs. Intervals resample",
        "**seeds (runs)**, not proposals -- proposals within a run are correlated",
        "by a shared RNG stream, so resampling them would understate the interval.",
        f"Bootstrap: B={N_BOOT:,} percentile method.",
        "",
        "| quorum | apath_frac | p_abstain | n runs | turnout | pass rate | quorum-fail | deadlock |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| (no data) | | | | | | | |")
        return lines

    for (q, ap, pa), grp in sorted(
        group_by(rows, ("quorum_pct", "apath_frac", "p_abstain")).items(),
        key=lambda kv: (float(kv[0][0]), float(kv[0][1]), float(kv[0][2])),
    ):
        turnout = _mean_vals(_numeric(grp, "mean_turnout"))
        # Order must match the header exactly: pass, quorum-fail, deadlock.
        # Emitting them in METRICS order (which lists deadlock before
        # quorum_fail) silently transposes the two columns and inverts the
        # headline finding, so the columns are named explicitly here.
        p_lo, p_mid, p_hi = bootstrap_ci_vals(_numeric(grp, "pass_rate"), rng)
        qf_lo, qf_mid, qf_hi = bootstrap_ci_vals(
            _numeric(grp, "quorum_fail_rate"), rng
        )
        dl_lo, dl_mid, dl_hi = bootstrap_ci_vals(
            _numeric(grp, "deadlock_rate"), rng
        )
        lines.append(
            f"| {q} | {ap} | {pa} | {len(grp)} | {fmt(turnout)} | "
            f"{fmt(p_mid)} [{fmt(p_lo)}, {fmt(p_hi)}] | "
            f"{fmt(qf_mid)} [{fmt(qf_lo)}, {fmt(qf_hi)}] | "
            f"{fmt(dl_mid)} [{fmt(dl_lo)}, {fmt(dl_hi)}] |"
        )
        print(f"[ci] apathy cell {q}/{ap}/{pa}", flush=True)
    return lines


def report_gov(rng: random.Random) -> list[str]:
    """Table 2: base governance sweep, showing where quorum is inert."""
    rows = load_rows("gov_sweep.csv")
    lines = [
        "",
        "## Table 2: base sweep -- quorum is inert at full mobilisation",
        "",
        f"Source: `gov_sweep.csv`, {len(rows)} runs. When `apath_frac=0` every",
        "member votes, so turnout saturates above any quorum and the threshold",
        "cannot bind. The flat pass rate below is therefore a real property of a",
        "fully-mobilised collective, not a bug -- but it also means this regime",
        "carries no information about quorum choice.",
        "",
        "| apath_frac | quorum | n runs | turnout | pass rate | quorum-fail |",
        "|---|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| (no data) | | | | | |")
        return lines

    for (ap, q), grp in sorted(
        group_by(rows, ("apath_frac", "quorum_pct")).items(),
        key=lambda kv: (float(kv[0][0]), float(kv[0][1])),
    ):
        # gov_sweep.csv has no mean_turnout column; report it as absent rather
        # than silently printing a blank that looks like low turnout.
        turnout_col = "mean_turnout" if "mean_turnout" in grp[0] else None
        turnout = (
            _mean_vals(_numeric(grp, turnout_col)) if turnout_col else float("nan")
        )
        p_lo, p_mid, p_hi = bootstrap_ci_vals(_numeric(grp, "pass_rate"), rng)
        qf_lo, qf_mid, qf_hi = bootstrap_ci_vals(
            _numeric(grp, "quorum_fail_rate"), rng
        )
        lines.append(
            f"| {ap} | {q} | {len(grp)} | {fmt(turnout)} | "
            f"{fmt(p_mid)} [{fmt(p_lo)}, {fmt(p_hi)}] | "
            f"{fmt(qf_mid)} [{fmt(qf_lo)}, {fmt(qf_hi)}] |"
        )
        print(f"[ci] gov cell {ap}/{q}", flush=True)
    return lines


def report_voting(rng: random.Random) -> list[str]:
    """Table 3: night-3 voting rules with cluster-bootstrap 95% CIs."""
    rows = load_rows("night3/voting_sweep.csv")
    lines = [
        "",
        "## Table 3: voting rules -- cluster bootstrap (resample = seed)",
        "",
        "Source: `night3/voting_sweep.csv`, {n} runs. Club-scale",
        "collectives (N in {5,9,15,30}) with sincere preferences and an apathy",
        "abstention model. Resampling unit: seed.",
        "",
        "| rule | p_abstain | n runs | turnout | pass rate | tie rate | minority-win |",
        "|---|---|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| (no data) | | | | | | |")
        return lines

    for (rule, pa), grp in sorted(
        group_by(rows, ("voting_rule", "p_abstain")).items()
    ):
        turnout = _mean_vals(_numeric(grp, "mean_turnout"))
        p = bootstrap_ci_vals(_numeric(grp, "pass_rate"), rng)
        t = bootstrap_ci_vals(_numeric(grp, "tie_rate"), rng)
        m = bootstrap_ci_vals(_numeric(grp, "minority_win_rate"), rng)
        lines.append(
            f"| {rule} | {pa} | {len(grp)} | {fmt(turnout)} | "
            f"{fmt(p[1])} [{fmt(p[0])}, {fmt(p[2])}] | "
            f"{fmt(t[1])} [{fmt(t[0])}, {fmt(t[2])}] | "
            f"{fmt(m[1])} [{fmt(m[0])}, {fmt(m[2])}] |"
        )
        print(f"[ci] voting cell {rule}/{pa}", flush=True)
    return lines


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261014)
    lines: list[str] = []
    # Build each table and flush it to disk immediately. If the process is
    # killed mid-sweep (this is CPU-heavy work), partial tables survive rather
    # than losing the whole run -- the failure mode that lost night 1's data.
    # NOTE: each table is a SEPARATE file. Earlier code wrote all three tables
    # to tab1_quorum_pathologies.md in sequence, so only the last (voting)
    # table survived and Tables 1-2 were silently discarded.
    lines = report_apathy(rng)
    (OUT / "tab1_quorum_pathologies.md").write_text("\n".join(lines) + "\n")
    print(f"[ci] wrote apathy table ({len(lines)} lines)", flush=True)
    lines = report_gov(rng)
    (OUT / "tab2_base_sweep.md").write_text("\n".join(lines) + "\n")
    print(f"[ci] wrote gov table ({len(lines)} lines)", flush=True)
    lines = report_voting(rng)
    (OUT / "tab3_voting_rules.md").write_text("\n".join(lines) + "\n")
    print(f"[ci] wrote voting table ({len(lines)} lines)", flush=True)


if __name__ == "__main__":
    main()
