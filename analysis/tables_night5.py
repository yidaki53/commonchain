"""Night 5, Job 5: result tables with cluster-bootstrap CIs.

Produces four new tables plus two CI upgrades of night-2's point-estimate
tables (the bootstrap machinery in analysis/confidence.py was written for
night-1/3 data but never applied to the mandate and delegation sweeps, so
those tables are currently point estimates without intervals -- not yet
citable as effects).

  tab5_fragmentation.md   voting rules under bloc structure (night 5)
  tab6_capture.md         constitutional capture phase diagram (night 5)
  tab7_deleg_blocs.md     aligned vs random delegation (night 5)
  tab8_mandate_ci.md      night-2 mandate sweep WITH CIs (upgrade)
  tab9_delegation_ci.md   night-2 delegation sweep WITH CIs (upgrade)

Resampling unit = seed (cluster bootstrap), night-1's convention: each row is
one run of correlated decisions sharing an RNG stream, so runs -- not
proposals -- are the honest unit of variation. Each table is flushed to its
OWN file immediately so a mid-run kill cannot discard completed tables
(night-3 lesson). Pure re-analysis: safe to re-run any time.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from analysis.confidence import _numeric, bootstrap_ci_vals, group_by

ROOT = Path(__file__).resolve().parent.parent
N5 = ROOT / "results" / "night5"
N2 = ROOT / "results" / "night2"
RNG = random.Random(20261016)


def load(path: Path, *valid: str) -> list[dict]:
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open()))
    if not valid:
        return rows
    # Failed cells carry -1 sentinels; exclude on the first named column.
    return [r for r in rows if r.get(valid[0]) not in (None, "", "-1")]


def fmt(v: float) -> str:
    return "nan" if v != v else f"{v:.3f}"


def ci(col: str, grp: list[dict]) -> str:
    lo, mid, hi = bootstrap_ci_vals(_numeric(grp, col), RNG)
    return f"{fmt(mid)} [{fmt(lo)}, {fmt(hi)}]"


def mean(col: str, grp: list[dict]) -> float:
    vals = _numeric(grp, col)
    return sum(vals) / len(vals) if vals else float("nan")


def _write(name: str, lines: list[str]) -> None:
    N5.mkdir(parents=True, exist_ok=True)
    p = N5 / name
    p.write_text("\n".join(lines) + "\n")
    print(f"[tables] wrote {p} ({len(lines)} lines)", flush=True)


def table_fragmentation() -> list[str]:
    rows = load(N5 / "fragmentation_sweep.csv", "pass_rate")
    lines = [
        "# Table 5: voting rules under fragmented preferences",
        "",
        f"Source: `night5/fragmentation_sweep.csv`, {len(rows)} runs.",
        "Bloc-structured sincere preferences (bloc 0 = targeted minority);",
        "minority-win = decided proposals won by a bloc with <50% of cast",
        "ballots. Binary cannot produce one by construction (pass needs",
        ">=50% of cast) -- the citable contrast. Cluster bootstrap,",
        "resample = seed.",
        "",
        "| rule | blocs | noise | abstain | n | pass | tie | minority-win"
        " | satisfaction | coherence |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | | | | | |"]
    for (rule, k, nz, pa), grp in sorted(
        group_by(rows, ("voting_rule", "n_blocs", "p_noise", "p_abstain")).items()
    ):
        lines.append(
            f"| {rule} | {k} | {nz} | {pa} | {len(grp)} | "
            f"{ci('pass_rate', grp)} | {ci('tie_rate', grp)} | "
            f"{ci('minority_win_rate', grp)} | "
            f"{ci('mean_satisfaction', grp)} | "
            f"{ci('coherence_rate', grp)} |"
        )
        print(f"[tables] frag cell {rule}/{k}/{nz}/{pa}", flush=True)
    return lines


def table_capture() -> list[str]:
    rows = load(N5 / "amendment_sweep.csv", "captured_any")
    lines = [
        "",
        "# Table 6: constitutional capture of the amendable policy layer",
        "",
        f"Source: `night5/amendment_sweep.csv`, {len(rows)} runs. A",
        "disciplined bloc proposes 'lower supermajority to 50' until it",
        "passes; afterwards an engaged honest majority (turnout 0.8) tries to",
        "restore. capture = ever passed; restore = ever recovered. All chains",
        "verified after every round (`chain_ok` asserted in sweep).",
        "",
        "| n | super | hostile | turnout | n | capture | first-capture"
        " round | restore |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | | | |"]
    for (n, s, h, t), grp in sorted(
        group_by(rows, ("n_members", "supermajority_pct", "hostile_frac",
                        "honest_turnout")).items(),
        key=lambda kv: (int(kv[0][0]), float(kv[0][1]), float(kv[0][2]),
                        float(kv[0][3])),
    ):
        firsts = [r for r in _numeric(grp, "first_capture") if r >= 0]
        fc = sum(firsts) / len(firsts) if firsts else float("nan")
        lines.append(
            f"| {n} | {s} | {h} | {t} | {len(grp)} | "
            f"{ci('captured_any', grp)} | {fmt(fc)} | "
            f"{ci('n_restores', grp)} |"
        )
        print(f"[tables] capture cell {n}/{s}/{h}/{t}", flush=True)
    return lines


def table_deleg_blocs() -> list[str]:
    rows = load(N5 / "deleg_blocs_sweep.csv", "deleg_pass")
    lines = [
        "",
        "# Table 7: preference-aligned vs random delegation",
        "",
        f"Source: `night5/deleg_blocs_sweep.csv`, {len(rows)} runs.",
        "`aligned_frac` = probability a delegator picks a delegate from their",
        "own bloc (0.0 = night-2's random model). delta pass = delegated -",
        "baseline on paired independent RNG streams; fidelity = carried",
        "ballots whose delegate shares the delegator's bloc. Cluster",
        "bootstrap, resample = seed.",
        "",
        "| abstain | rate | aligned | depth | n | delta pass | fidelity"
        " | q-fail (deleg) | max delegate share |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | | | | |"]
    for (pa, rate, al, d), grp in sorted(
        group_by(rows, ("p_abstain", "delegation_rate", "aligned_frac",
                        "max_depth")).items()
    ):
        deltas = [
            float(r["deleg_pass"]) - float(r["baseline_pass"]) for r in grp
        ]
        lo, mid, hi = bootstrap_ci_vals(deltas, RNG)
        lines.append(
            f"| {pa} | {rate} | {al} | {d} | {len(grp)} | "
            f"{fmt(mid)} [{fmt(lo)}, {fmt(hi)}] | "
            f"{ci('fidelity', grp)} | {ci('deleg_qfail', grp)} | "
            f"{ci('max_delegate_share', grp)} |"
        )
        print(f"[tables] delegbloc cell {pa}/{rate}/{al}/{d}", flush=True)
    return lines


def table_mandate_ci() -> list[str]:
    rows = load(N2 / "mandate_sweep.csv", "n_granted")
    lines = [
        "",
        "# Table 8: mandate rotation with incumbency -- WITH CIs (upgrade)",
        "",
        f"Source: `night2/mandate_sweep.csv`, {len(rows)} runs. Same data as",
        "night-2's point-estimate table, now with cluster-bootstrap 95%",
        "intervals over seeds -- night-2's mandate/delegation tables were",
        "written before the CI machinery was wired to them, so their effects",
        "were not yet citable. max holder share = largest single member's",
        "share of granted mandates (1/n = perfect rotation).",
        "",
        "| n | term | p_incumbent | n runs | max holder share | HHI |",
        "|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | |"]
    for (n, term, p), grp in sorted(
        group_by(rows, ("n_members", "term_blocks", "p_incumbent")).items(),
        key=lambda kv: (int(kv[0][0]), int(kv[0][1]), float(kv[0][2])),
    ):
        lines.append(
            f"| {n} | {term} | {p} | {len(grp)} | "
            f"{ci('max_holder_share', grp)} | "
            f"{ci('hhi_concentration', grp)} |"
        )
        print(f"[tables] mandate-ci cell {n}/{term}/{p}", flush=True)
    return lines


def table_delegation_ci() -> list[str]:
    rows = load(N2 / "delegation_sweep.csv", "baseline_pass_rate")
    lines = [
        "",
        "# Table 9: delegation trade (night-2 data) -- WITH CIs (upgrade)",
        "",
        f"Source: `night2/delegation_sweep.csv`, {len(rows)} runs. delta pass",
        "= delegated - baseline, paired independent RNG streams. Cluster",
        "bootstrap, resample = seed.",
        "",
        "| n | apath | p_abstain | rate (depth) | n runs | delta pass"
        " | q-fail (deleg) | max delegate share | HHI |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        return lines + ["| (no data) | | | | | | | | |"]
    for (n, ap, pa, rate, depth), grp in sorted(
        group_by(rows, ("n_members", "apath_frac", "p_abstain",
                        "delegation_rate", "max_depth")).items(),
        key=lambda kv: (int(kv[0][0]), float(kv[0][1]), float(kv[0][2]),
                        float(kv[0][3]), int(kv[0][4])),
    ):
        deltas = [
            float(r["delegated_pass_rate"]) - float(r["baseline_pass_rate"])
            for r in grp
        ]
        lo, mid, hi = bootstrap_ci_vals(deltas, RNG)
        lines.append(
            f"| {n} | {ap} | {pa} | {rate} (d={depth}) | {len(grp)} | "
            f"{fmt(mid)} [{fmt(lo)}, {fmt(hi)}] | "
            f"{ci('delegated_quorum_fail', grp)} | "
            f"{ci('max_delegate_share', grp)} | {ci('delegate_hhi', grp)} |"
        )
        print(f"[tables] deleg-ci cell {n}/{ap}/{pa}/{rate}", flush=True)
    return lines


def main() -> None:
    # Each table is its own file, flushed immediately (night-3 lesson).
    _write("tab5_fragmentation.md", table_fragmentation())
    _write("tab6_capture.md", table_capture())
    _write("tab7_deleg_blocs.md", table_deleg_blocs())
    _write("tab8_mandate_ci.md", table_mandate_ci())
    _write("tab9_delegation_ci.md", table_delegation_ci())


if __name__ == "__main__":
    main()
