"""Night-2 result tables: pass threshold, mandate incumbency, delegation trade.

Aggregates the night-2 sweep CSVs into Markdown tables. Pure re-analysis -- no
simulation -- so it is safe to re-run at any time as sweeps complete.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "night2"


def load(name: str) -> list[dict]:
    p = RESULTS / name
    if not p.exists():
        return []
    rows = list(csv.DictReader(p.open()))
    return [r for r in rows if r.get("pass_rate", "0") not in ("-1", "", None)]


def mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def group(rows, keys):
    out = defaultdict(list)
    for r in rows:
        out[tuple(r[k] for k in keys)].append(r)
    return out


def table_pass() -> list[str]:
    rows = load("pass_sweep.csv")
    lines = [
        "# Table 2: pass_pct sweep -- is 50% actually the right default?",
        "",
        f"Source: `pass_sweep.csv`, {len(rows)} runs. Night 1 hardcoded",
        "`pass_pct=50.0` while sweeping quorum, so the recommendation to ship it",
        "had no evidence behind it. This table is the evidence, whatever it says.",
        "",
        "| n | quorum | pass_pct | apath | p_abstain | turnout | pass rate | quorum-fail |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | | |"]
    for (n, q, pp, ap, pa), grp in sorted(
        group(rows, ("n_members", "quorum_pct", "pass_pct", "apath_frac", "p_abstain")).items(),
        key=lambda kv: (int(kv[0][0]), float(kv[0][1]), float(kv[0][2]),
                        float(kv[0][3]), float(kv[0][4])),
    ):
        lines.append(
            f"| {n} | {q} | {pp} | {ap} | {pa} | "
            f"{mean([float(r['mean_turnout']) for r in grp]):.3f} | "
            f"{mean([float(r['pass_rate']) for r in grp]):.3f} | "
            f"{mean([float(r['quorum_fail_rate']) for r in grp]):.3f} |"
        )
    return lines


def table_mandate() -> list[str]:
    rows = load("mandate_sweep.csv")
    lines = [
        "",
        "## Table 3: mandate rotation with an incumbency advantage",
        "",
        f"Source: `mandate_sweep.csv`, {len(rows)} runs. `p_incumbent` is the",
        "probability the current holder is re-nominated. Night 1 omitted this,",
        "which made HHI flat across term lengths by construction and the result",
        "uncitable. With incumbency modelled, term length has something to bite on.",
        "",
        "| n | term | p_incumbent | max holder share | HHI | lapses |",
        "|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | |"]
    for (n, term, p), grp in sorted(
        group(rows, ("n_members", "term_blocks", "p_incumbent")).items(),
        key=lambda kv: (int(kv[0][0]), int(kv[0][1]), float(kv[0][2])),
    ):
        lines.append(
            f"| {n} | {term} | {p} | "
            f"{mean([float(r['max_holder_share']) for r in grp]):.3f} | "
            f"{mean([float(r['hhi_concentration']) for r in grp]):.4f} | "
            f"{mean([float(r['n_lapsed']) for r in grp]):.1f} |"
        )
    return lines


def table_delegation() -> list[str]:
    rows = load("delegation_sweep.csv")
    lines = [
        "",
        "## Table 4: delegation -- turnout gain vs power concentration",
        "",
        f"Source: `delegation_sweep.csv`, {len(rows)} runs. Each row runs the same",
        "collective twice from independent RNG streams: baseline vs delegated.",
        "`delta pass` is the whole point of the table; `max delegate share` is its",
        "cost. Delegate weight is pinned to 1, so a delegate representing many",
        "members still casts one ballot.",
        "",
        "| n | apath | p_abstain | deleg_rate | base pass | deleg pass | delta | base q-fail | deleg q-fail | max deleg share |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | | | | |"]
    for (n, ap, pa, rate, depth), grp in sorted(
        group(rows, ("n_members", "apath_frac", "p_abstain", "delegation_rate", "max_depth")).items(),
        key=lambda kv: (int(kv[0][0]), float(kv[0][1]), float(kv[0][2]),
                        float(kv[0][3]), int(kv[0][4])),
    ):
        b = mean([float(r["baseline_pass_rate"]) for r in grp])
        d = mean([float(r["delegated_pass_rate"]) for r in grp])
        lines.append(
            f"| {n} | {ap} | {pa} | {rate} (d={depth}) | {b:.3f} | {d:.3f} | "
            f"{d - b:+.3f} | "
            f"{mean([float(r['baseline_quorum_fail']) for r in grp]):.3f} | "
            f"{mean([float(r['delegated_quorum_fail']) for r in grp]):.3f} | "
            f"{mean([float(r['max_delegate_share']) for r in grp]):.3f} |"
        )
    return lines


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    lines = table_pass() + table_mandate() + table_delegation()
    out = RESULTS / "tab2_pass_threshold.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"[tables] wrote {out}", flush=True)
    for ln in lines:
        print(ln, flush=True)


if __name__ == "__main__":
    main()
