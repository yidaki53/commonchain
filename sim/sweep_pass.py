"""pass_pct sweep -- tests the charter default the night-1 run never varied.

Night 1's `gov_grid` hardcoded ``pass_pct: 50.0`` while sweeping quorum. So the
headline finding ("raising quorum buys paralysis") has evidence behind it, but
the recommendation to ship ``pass_pct=50`` had none. This sweep exists to either
justify that default or overturn it -- it is deliberately set up so a null or
contradictory result is a real outcome, not a failure.

Writes to ``results/night2/pass_sweep.csv`` with its own state file, so a smoke
test cannot poison the grid (the night-1 truncation bug).
"""

from __future__ import annotations

import csv
import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sim.governance_sim import SimConfig, run_collective  # noqa: E402

OUT = ROOT / "results" / "night2" / "pass_sweep.csv"
STATE = ROOT / "results" / "night2" / "pass_state.json"

FIELDS = [
    "n_members", "quorum_pct", "pass_pct", "apath_frac", "p_abstain",
    "seed", "pass_rate", "deadlock_rate", "quorum_fail_rate",
    "adversarial_win_rate", "mean_turnout", "elapsed_s",
]


def grid(seeds: int) -> list[dict]:
    cells = []
    for n, quorum, pass_pct, apath, p_abstain in itertools.product(
        [3, 5, 9, 15, 25, 51],
        [50.0, 66.0],
        [50.0, 55.0, 60.0, 66.0],
        [0.2, 0.5, 0.7],
        [0.8, 0.95],
    ):
        for s in range(seeds):
            cells.append({
                "n_members": n,
                "quorum_pct": quorum,
                "pass_pct": pass_pct,
                "apath_frac": apath,
                "p_abstain": p_abstain,
                "seed": s,
            })
    return cells


def key(c: dict) -> str:
    return (
        f"{c['n_members']}/{c['quorum_pct']}/{c['pass_pct']}/"
        f"{c['apath_frac']}/{c['p_abstain']}/{c['seed']}"
    )


def main() -> None:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cells = grid(seeds)
    done: set[str] = set()
    if STATE.exists():
        done = set(json.loads(STATE.read_text()).get("pass_done", []))
    fresh = [c for c in cells if key(c) not in done]
    print(f"[pass] {len(cells)} cells, {len(done)} done, {len(fresh)} fresh",
          flush=True)

    fresh = fresh[: int(sys.argv[2])] if len(sys.argv) > 2 else fresh
    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if OUT.stat().st_size == 0:
            w.writeheader()
        for i, c in enumerate(fresh):
            t0 = time.time()
            try:
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
            except Exception as e:  # one bad cell must never kill the night
                row = {**c, "pass_rate": -1, "deadlock_rate": -1,
                       "quorum_fail_rate": -1, "adversarial_win_rate": -1,
                       "mean_turnout": -1, "elapsed_s": 0}
                print(f"[pass] cell failed {c}: {e}", flush=True)
            w.writerow(row)
            f.flush()
            done.add(key(c))
            if (i + 1) % 200 == 0:
                STATE.write_text(json.dumps({"pass_done": sorted(done)}))
                print(f"[pass] {i + 1}/{len(fresh)}", flush=True)
    STATE.write_text(json.dumps({"pass_done": sorted(done)}))
    print(f"[pass] done. rows in {OUT}", flush=True)


if __name__ == "__main__":
    main()
