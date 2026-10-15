"""Targeted supplementary sweep: the quorum-binding region.

The overnight grid (`gov_grid`) varied apathy only up to 0.4 with
p_abstain=0.8, which floors turnout near 68% -- above every quorum tested, so
quorum could never bind and `quorum_fail_rate` was identically 0. That is a
non-finding, not evidence that quorum is harmless.

This job deliberately probes the binding region: high apathy, high abstention
probability, high quorum, across scales. Appends to results/gov_apathy_sweep.csv
so it never collides with the overnight CSV.
"""

from __future__ import annotations

import csv
import itertools
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sim.governance_sim import SimConfig, run_collective  # noqa: E402

OUT = ROOT / "results" / "gov_apathy_sweep.csv"
FIELDS = [
    "n_members", "quorum_pct", "adversarial_frac", "apath_frac",
    "p_abstain", "p_yes", "seed", "pass_rate", "deadlock_rate",
    "quorum_fail_rate", "adversarial_win_rate", "mean_turnout", "elapsed_s",
]


def grid(seeds: int) -> list[dict]:
    cells = []
    for n, quorum, apath, p_abstain in itertools.product(
        [3, 5, 9, 15, 25, 51],
        [50.0, 66.0, 75.0],
        [0.2, 0.5, 0.7],
        [0.8, 0.95],
    ):
        for s in range(seeds):
            cells.append({
                "n_members": n,
                "quorum_pct": quorum,
                "adversarial_frac": 0.0,
                "apath_frac": apath,
                "p_abstain": p_abstain,
                "p_yes": 0.6,
                "seed": s,
            })
    return cells


def main() -> None:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    cells = grid(seeds)
    print(f"[apathy] {len(cells)} cells", flush=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, c in enumerate(cells):
            t0 = time.time()
            res = run_collective(SimConfig(**c, n_proposals=20))
            row = {
                **c,
                "pass_rate": round(res.pass_rate, 4),
                "deadlock_rate": round(res.deadlock_rate, 4),
                "quorum_fail_rate": round(res.quorum_fail_rate, 4),
                "adversarial_win_rate": round(res.adversarial_win_rate, 4),
                "mean_turnout": round(res.turnout_mean, 4),
                "elapsed_s": round(time.time() - t0, 3),
            }
            w.writerow(row)
            if (i + 1) % 200 == 0:
                print(f"[apathy] {i + 1}/{len(cells)}", flush=True)
    print(f"[apathy] done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
