"""Night 5, Job 6: figures for the night-5 results.

Three citable figures, each from a single sweep CSV:

  fig8_fragmentation.png  minority-win and tie rate by voting rule, faceted
                          by preference noise (the fragmented-preference fix
                          for night 3's zero-by-construction caveat);
  fig9_capture.png        constitutional-capture phase diagram: capture rate
                          over bloc size x honest turnout, one panel per
                          supermajority default;
  fig10_verify_scaling.png  verify() grows linearly with chain length while
                          verify_block() stays flat (log-log) -- the O(n)
                          vs O(1) engineering claim as a curve, not a point.

Deterministic (no RNG); safe to re-run at any time. Missing CSV -> figure
skipped with a note, never a crash.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
N5 = ROOT / "results" / "night5"
FIG = N5  # same convention as nights 3/4: figures next to their tables


def load(name: str) -> list[dict]:
    p = N5 / name
    if not p.exists():
        print(f"[figs] missing {p}, skipping", flush=True)
        return []
    return list(csv.DictReader(p.open()))


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def fig_fragmentation(rows: list[dict]) -> None:
    rows = [r for r in rows if r.get("pass_rate") not in (None, "", "-1")]
    if not rows:
        print("[figs] no fragmentation data", flush=True)
        return
    # Group by (rule, noise): collapse over blocs/abstain/N, keep the means.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["voting_rule"], float(r["p_noise"]))].append(r)
    noises = sorted({k[1] for k in groups})
    fig, axes = plt.subplots(1, len(noises), figsize=(4.2 * len(noises), 4),
                             sharey=True, squeeze=False)
    for ax, nz in zip(axes[0], noises):
        rules = ["binary", "plurality", "approval"]
        minor = [
            _mean([float(r["minority_win_rate"])
                   for r in groups[(rule, nz)]])
            for rule in rules
        ]
        tie = [
            _mean([float(r["tie_rate"]) for r in groups[(rule, nz)]])
            for rule in rules
        ]
        x = range(len(rules))
        ax.bar([i - 0.19 for i in x], minor, 0.36, label="minority win",
               color="#c44e52")
        ax.bar([i + 0.19 for i in x], tie, 0.36, label="tie/deadlock",
               color="#8172b3")
        ax.set_xticks(list(x))
        ax.set_xticklabels(rules)
        ax.set_title(f"cross-pressure noise = {nz}")
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.3)
    axes[0][0].set_ylabel("rate (of proposals)")
    axes[0][-1].legend(loc="upper right", fontsize=8)
    fig.suptitle("Voting rules under fragmented preferences "
                 "(binary minority-win is 0 by construction)")
    fig.tight_layout()
    out = FIG / "fig8_fragmentation.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"[figs] wrote {out}", flush=True)


def fig_capture(rows: list[dict]) -> None:
    rows = [r for r in rows if r.get("captured_any") not in (None, "", "-1")]
    if not rows:
        print("[figs] no capture data", flush=True)
        return
    supers = sorted({float(r["supermajority_pct"]) for r in rows})
    fracs = sorted({float(r["hostile_frac"]) for r in rows})
    turns = sorted({float(r["honest_turnout"]) for r in rows})
    fig, axes = plt.subplots(1, len(supers), figsize=(4.0 * len(supers), 3.6),
                             sharey=True, squeeze=False)
    for ax, s in zip(axes[0], supers):
        # capture rate over (hostile_frac x honest_turnout)
        grid_vals = [
            [
                _mean([float(r["captured_any"]) for r in rows
                       if float(r["supermajority_pct"]) == s
                       and float(r["hostile_frac"]) == h
                       and float(r["honest_turnout"]) == t])
                for t in turns
            ]
            for h in fracs
        ]
        im = ax.imshow(grid_vals, vmin=0.0, vmax=1.0, cmap="RdYlGn_r",
                       aspect="auto")
        ax.set_xticks(range(len(turns)))
        ax.set_xticklabels([f"{t:.1f}" for t in turns])
        ax.set_yticks(range(len(fracs)))
        ax.set_yticklabels([f"{h:.2f}" for h in fracs])
        ax.set_xlabel("honest turnout")
        ax.set_title(f"supermajority {s:.0f}%")
        for i in range(len(fracs)):
            for j in range(len(turns)):
                ax.text(j, i, f"{grid_vals[i][j]:.2f}", ha="center",
                        va="center", fontsize=8)
    axes[0][0].set_ylabel("hostile bloc share")
    fig.colorbar(im, ax=axes, shrink=0.85, label="capture rate")
    fig.suptitle("Constitutional capture: a disciplined minority lowers the"
                 " supermajority (rate over 40 rounds)")
    fig.subplots_adjust(left=0.08, right=0.9, top=0.82, bottom=0.12)
    out = FIG / "fig9_capture.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"[figs] wrote {out}", flush=True)


def fig_verify(rows: list[dict]) -> None:
    rows = [r for r in rows if r.get("chain_length") not in (None, "")]
    if not rows:
        print("[figs] no verify bench data", flush=True)
        return
    rows.sort(key=lambda r: int(r["chain_length"]))
    L = [int(r["chain_length"]) for r in rows]
    full_us = [float(r["verify_full_us_per_block"]) for r in rows]
    block_us = [float(r["verify_block_us"]) for r in rows]
    fig, ax = plt.subplots(figsize=(5.6, 4))
    ax.loglog(L, full_us, "o-", color="#4c72b0",
              label="verify() per block (O(n) total)")
    ax.loglog(L, block_us, "s-", color="#c44e52",
              label="verify_block() (O(1))")
    ax.set_xlabel("chain length (blocks)")
    ax.set_ylabel("time per check (us)")
    ax.set_title("Verification scaling: full-chain vs single-block")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = FIG / "fig10_verify_scaling.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"[figs] wrote {out}", flush=True)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig_fragmentation(load("fragmentation_sweep.csv"))
    fig_capture(load("amendment_sweep.csv"))
    fig_verify(load("verify_bench.csv"))


if __name__ == "__main__":
    main()
