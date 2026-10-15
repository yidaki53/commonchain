"""Render figures + tables from overnight sweep CSVs.

Usage: python3 analysis/make_figures.py
Reads results/*.csv, writes results/*.png + results/*.md.
Safe to run repeatedly; skips missing inputs with a warning.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: must precede the pyplot import
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[fig] missing {path}, skipping", flush=True)
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def _f(rows: list[dict], key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get(key) not in ("", "-1", None)]


def fig_gov_heatmap(rows: list[dict]) -> None:
    """Mean pass rate by (quorum x adversarial_frac), honest baseline."""
    if not rows:
        return
    quorums = sorted({float(r["quorum_pct"]) for r in rows})
    advs = sorted({float(r["adversarial_frac"]) for r in rows})
    z = []
    for q in quorums:
        row = []
        for a in advs:
            vals = _f(
                [r for r in rows
                 if float(r["quorum_pct"]) == q
                 and float(r["adversarial_frac"]) == a
                 and float(r["apath_frac"]) == 0.0],
                "pass_rate",
            )
            row.append(sum(vals) / len(vals) if vals else 0.0)
        z.append(row)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    im = ax.imshow(z, vmin=0, vmax=1, aspect="auto", origin="lower")
    ax.set_xticks(range(len(advs)), [str(a) for a in advs])
    ax.set_yticks(range(len(quorums)), [str(q) for q in quorums])
    ax.set_xlabel("adversarial fraction")
    ax.set_ylabel("quorum %")
    ax.set_title("Mean pass rate (no apathy) — gov_sweep")
    fig.colorbar(im, ax=ax, label="pass rate")
    fig.tight_layout()
    fig.savefig(RESULTS / "fig1_gov_heatmap.png", dpi=120)
    plt.close(fig)
    print("[fig] fig1_gov_heatmap.png", flush=True)


def fig_payroll(rows: list[dict]) -> None:
    """Gini vs stable_base_share per policy (n=10, pareto hours)."""
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for policy in ("equal", "labor_hours", "seniority"):
        sub = [r for r in rows
               if r["policy"] == policy and r["n"] == "10"
               and r["hours_dist"] == "pareto"]
        xs = sorted({float(r["stable_base_share"]) for r in sub})
        ys = []
        for x in xs:
            vals = _f([r for r in sub if float(r["stable_base_share"]) == x], "gini")
            ys.append(sum(vals) / len(vals) if vals else 0.0)
        ax.plot(xs, ys, marker="o", label=policy)
    ax.set_xlabel("stable_base_share")
    ax.set_ylabel("mean Gini of payouts")
    ax.set_title("Payroll fairness (n=10, pareto hours)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "fig2_payroll_fairness.png", dpi=120)
    plt.close(fig)
    print("[fig] fig2_payroll_fairness.png", flush=True)


def fig_mandate(rows: list[dict]) -> None:
    """HHI concentration vs term_blocks (n=15)."""
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    sub = [r for r in rows if r["n_members"] == "15"]
    xs = sorted({int(r["term_blocks"]) for r in sub})
    ys = []
    for x in xs:
        vals = _f([r for r in sub if int(r["term_blocks"]) == x], "hhi_concentration")
        ys.append(sum(vals) / len(vals) if vals else 0.0)
    ax.plot(xs, ys, marker="o")
    ax.axhline(1 / 15, color="gray", linestyle="--", label="perfect rotation (1/n)")
    ax.set_xlabel("term_blocks")
    ax.set_ylabel("mean HHI concentration")
    ax.set_title("Mandate concentration vs term length (n=15)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "fig3_mandate_rotation.png", dpi=120)
    plt.close(fig)
    print("[fig] fig3_mandate_rotation.png", flush=True)


def tab_quorum(rows: list[dict]) -> None:
    """Markdown table: quorum pathologies at baseline (n=9, honest)."""
    if not rows:
        return
    lines = [
        "# Quorum pathologies (n=9, honest majority, 20 proposals)",
        "",
        "| quorum % | pass rate | quorum-fail rate | deadlock rate |",
        "|---|---|---|---|",
    ]
    for q in sorted({float(r["quorum_pct"]) for r in rows}):
        sub = [r for r in rows
               if float(r["quorum_pct"]) == q
               and r["n_members"] == "9"
               and float(r["adversarial_frac"]) == 0.0
               and float(r["apath_frac"]) == 0.0]
        if not sub:
            continue
        mp = sum(_f(sub, "pass_rate")) / len(sub)
        mq = sum(_f(sub, "quorum_fail_rate")) / len(sub)
        md = sum(_f(sub, "deadlock_rate")) / len(sub)
        lines.append(f"| {q:g} | {mp:.2f} | {mq:.2f} | {md:.2f} |")
    (RESULTS / "night2" / "tab1_quorum_pathologies.md").write_text("\n".join(lines) + "\n")
    print("[fig] night2/tab1_quorum_pathologies.md", flush=True)


def fig_voting(rows: list[dict]) -> None:
    """Fig 6 (night 3): pass rate by voting rule across apathy levels.

    One curve per rule (binary / plurality / approval), averaged over
    collective sizes and seeds. Ties are recorded, never broken, so the
    plurality/approval curves sit below binary at zero abstention -- the
    honest cost of multi-option choice.
    """
    if not rows:
        print("[fig] no voting rows, skipping fig6", flush=True)
        return
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 4.4))
    colors = {"binary": "#1b7837", "plurality": "#762a83", "approval": "#2166ac"}
    for rule in ("binary", "plurality", "approval"):
        sub = [r for r in rows if r.get("voting_rule") == rule]
        if not sub:
            continue
        pas = sorted({float(r["p_abstain"]) for r in sub})
        ys = []
        for pa in pas:
            vals = _f([r for r in sub if float(r["p_abstain"]) == pa], "pass_rate")
            ys.append(sum(vals) / len(vals) if vals else 0.0)
        ax.plot(pas, ys, "o-", color=colors[rule], label=rule)
    ax.set_xlabel("p_abstain")
    ax.set_ylabel("mean pass rate")
    ax.set_title("A. Pass rate vs abstention, by rule")
    ax.set_ylim(0, 1)
    ax.legend()
    ax.grid(alpha=0.3)
    for rule in ("binary", "plurality", "approval"):
        sub = [r for r in rows if r.get("voting_rule") == rule]
        if not sub:
            continue
        tvals = _f(sub, "tie_rate")
        mvals = _f(sub, "minority_win_rate")
        t = sum(tvals) / len(tvals) if tvals else 0.0
        m = sum(mvals) / len(mvals) if mvals else 0.0
        ax2.bar([f"{rule}\ntie", f"{rule}\nminority-win"], [t, m],
                color=[colors[rule], "gray"], alpha=0.85)
    ax2.set_title("B. Tie rate and minority-win rate, by rule")
    ax2.set_ylabel("rate")
    ax2.set_ylim(0, 1)
    ax2.grid(alpha=0.3, axis="y")
    fig.suptitle("Fig 6: voting rules under apathy (night 3 sweep)", fontsize=12)
    fig.tight_layout()
    out = RESULTS / "night3" / "fig6_voting_rules.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[fig] {out}", flush=True)


def fig_apathy(rows: list[dict]) -> None:
    """Fig 5: pass rate collapses as apathy rises; quorum cannot rescue it."""
    ap = [r for r in rows if "p_abstain" in r]
    if not ap:
        print("[fig] no apathy rows, skipping fig5", flush=True)
        return

    # mean per (quorum, apath_frac, p_abstain)
    agg: dict[tuple[float, float, float], list[float]] = {}
    counts: dict[tuple[float, float, float], int] = {}
    for r in ap:
        k = (float(r["quorum_pct"]), float(r["apath_frac"]), float(r["p_abstain"]))
        vals = [
            float(r["pass_rate"]),
            float(r["quorum_fail_rate"]),
            float(r["deadlock_rate"]),
            float(r["mean_turnout"]),
        ]
        if k not in agg:
            agg[k] = vals
            counts[k] = 1
        else:
            agg[k] = [a + b for a, b in zip(agg[k], vals)]
            counts[k] += 1
    agg = {k: [v / counts[k] for v in vals] for k, vals in agg.items()}

    colors = {50.0: "#1b7837", 66.0: "#762a83", 75.0: "#b2182b"}
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))

    # Panel B (the clean curve): pass rate vs apath_frac, per quorum
    for q in sorted({k[0] for k in agg}):
        per_af: dict[float, list[float]] = {}
        for (qq, af, pa), v in agg.items():
            if qq == q:
                per_af.setdefault(af, []).append(v[0])
        xs = sorted(per_af)
        ys = [sum(per_af[a]) / len(per_af[a]) for a in xs]
        axes[1].plot(xs, ys, "o-", color=colors.get(q, "gray"), lw=2,
                     label=f"quorum {q:.0f}%")
    axes[1].axhline(0.5, color="black", ls=":", lw=1, label="50% pass rate")
    axes[1].set_title("B. Apathy is the binding constraint")
    axes[1].set_xlabel("apath_frac (share of structurally apathetic members)")
    axes[1].set_ylabel("pass rate")
    axes[1].set_ylim(0, 1)
    axes[1].legend(fontsize=7)
    axes[1].grid(alpha=0.3)

    # Panel A: scatter of every grid cell
    for (q, af, pa), v in sorted(agg.items()):
        axes[0].plot([af], [v[0]], "o", color=colors.get(q, "gray"),
                     alpha=0.75, ms=7)
    for q, c in colors.items():
        axes[0].plot([], [], "o", color=c, label=f"quorum {q:.0f}%")
    axes[0].set_title("A. Pass rate by apathy (each marker = p_abstain level)")
    axes[0].set_xlabel("apath_frac")
    axes[0].set_ylabel("pass rate")
    axes[0].set_ylim(0, 1)
    axes[0].legend(fontsize=7)
    axes[0].grid(alpha=0.3)

    # Panel C: which failure mode dominates across the whole grid
    n = len(agg)
    qfail = sum(v[1] for v in agg.values()) / n
    dead = sum(v[2] for v in agg.values()) / n
    axes[2].bar(
        ["quorum-fail\n(never decided)", "deadlock\n(decided: no)"],
        [qfail, dead],
        color=["#b2182b", "#2166ac"],
    )
    axes[2].set_title("C. Failure mode split (whole grid)")
    axes[2].set_ylabel("rate")
    axes[2].set_ylim(0, 1)
    axes[2].grid(alpha=0.3, axis="y")
    for i, v in enumerate([qfail, dead]):
        axes[2].text(i, v + 0.02, f"{v*100:.0f}%", ha="center", fontsize=10)

    fig.suptitle(
        "Fig 5: turnout, not disagreement, is what stops a bossless "
        "collective acting",
        fontsize=12,
    )
    fig.tight_layout()
    out = RESULTS / "fig5_apathy_quorum.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[fig] {out}", flush=True)


def main() -> None:
    gov = _read_csv(RESULTS / "gov_sweep.csv")
    pay = _read_csv(RESULTS / "payroll_sweep.csv")
    man = _read_csv(RESULTS / "mandate_sweep.csv")
    apathy = _read_csv(RESULTS / "gov_apathy_sweep.csv")
    fig_gov_heatmap(gov)
    fig_payroll(pay)
    fig_mandate(man)
    fig_apathy(apathy)
    tab_quorum(gov)
    fig_voting(_read_csv(RESULTS / "night3" / "voting_sweep.csv"))
    print("[fig] done", flush=True)


if __name__ == "__main__":
    main()
