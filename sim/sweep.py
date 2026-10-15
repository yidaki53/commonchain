"""Overnight sweep driver: grid search with checkpoint resume.

Usage:
    python3 sim/sweep.py --job gov|payroll|mandate [--cells N] [--seeds S]

Each job writes append-only CSV rows to results/ and records completed cells
in results/sweep_state.json, so a killed run resumes where it left off.
`--cells` caps the number of NEW cells (for smoke tests); default is the full
grid. `SEEDS` env var scales seeds per cell (default per job).
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sim.governance_sim import (  # noqa: E402
    SimConfig,
    run_collective,
    run_mandate_cell,
    run_payroll_cell,
)

RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
STATE_FILE = RESULTS / "sweep_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def append_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})


def gov_grid(seeds: int) -> list[dict]:
    cells = []
    for n, quorum, adv, apath in itertools.product(
        [3, 5, 9, 15, 25, 51, 101],
        [30.0, 40.0, 50.0, 60.0, 66.0],
        [0.0, 0.1, 0.2, 0.33],
        [0.0, 0.2, 0.4],
    ):
        for s in range(seeds):
            cells.append(
                {
                    "n_members": n,
                    "quorum_pct": quorum,
                    "pass_pct": 50.0,
                    "adversarial_frac": adv,
                    "apath_frac": apath,
                    "seed": s,
                }
            )
    return cells


def _gov_key(c: dict) -> str:
    return (
        f"{c['n_members']}/{c['quorum_pct']}/"
        f"{c['adversarial_frac']}/{c['apath_frac']}/{c['seed']}"
    )


def run_gov(max_cells: int | None, seeds: int) -> None:
    out = RESULTS / "gov_sweep.csv"
    fields = [
        "n_members", "quorum_pct", "pass_pct", "adversarial_frac",
        "apath_frac", "seed", "pass_rate", "deadlock_rate",
        "quorum_fail_rate", "adversarial_win_rate", "elapsed_s",
    ]
    state = load_state()
    done = set(state.get("gov_done", []))
    cells = gov_grid(seeds)
    print(f"[gov] {len(cells)} cells total, {len(done)} done", flush=True)
    fresh = [c for c in cells if _gov_key(c) not in done]
    if max_cells:
        fresh = fresh[:max_cells]
    batch: list[dict] = []
    for i, c in enumerate(fresh):
        t0 = time.time()
        try:
            res = run_collective(SimConfig(**c, n_proposals=20))
            row = {**c, "pass_rate": res.pass_rate,
                   "deadlock_rate": res.deadlock_rate,
                   "quorum_fail_rate": res.quorum_fail_rate,
                   "adversarial_win_rate": res.adversarial_win_rate,
                   "elapsed_s": round(time.time() - t0, 3)}
        except Exception as e:  # never let one cell kill the night
            row = {**c, "pass_rate": -1, "deadlock_rate": -1,
                   "quorum_fail_rate": -1, "adversarial_win_rate": -1,
                   "elapsed_s": round(time.time() - t0, 3)}
            print(f"[gov] cell failed {c}: {e}", flush=True)
        batch.append(row)
        done.add(_gov_key(c))
        if len(batch) >= 50:
            append_rows(out, batch, fields)
            batch = []
            state["gov_done"] = sorted(done)
            save_state(state)
        if (i + 1) % 200 == 0:
            print(f"[gov] {i + 1}/{len(fresh)} cells", flush=True)
    if batch:
        append_rows(out, batch, fields)
    state["gov_done"] = sorted(done)
    save_state(state)
    print(f"[gov] done. rows in {out}", flush=True)


def run_payroll(max_cells: int | None, seeds: int) -> None:
    out = RESULTS / "payroll_sweep.csv"
    fields = ["policy", "stable_base_share", "n", "hours_dist", "seed",
              "gini", "floor_violation_rate", "min_share", "max_share"]
    state = load_state()
    done = set(state.get("payroll_done", []))
    cells = [
        {"policy": p, "stable_base_share": round(b, 1), "n": n,
         "hours_dist": d, "seed": s}
        for p, b, n, d, s in itertools.product(
            ["equal", "labor_hours", "seniority"],
            [i / 10 for i in range(0, 11)],
            [3, 10, 50],
            ["uniform", "pareto", "bimodal"],
            range(seeds),
        )
    ]

    def _key(c: dict) -> str:
        return (f"{c['policy']}/{c['stable_base_share']}/"
                f"{c['n']}/{c['hours_dist']}/{c['seed']}")

    print(f"[payroll] {len(cells)} cells, {len(done)} done", flush=True)
    fresh = [c for c in cells if _key(c) not in done]
    if max_cells:
        fresh = fresh[:max_cells]
    batch = []
    for i, c in enumerate(fresh):
        try:
            row = run_payroll_cell(**c)
        except Exception as e:
            row = {**c, "gini": -1, "floor_violation_rate": -1,
                   "min_share": -1, "max_share": -1}
            print(f"[payroll] cell failed {c}: {e}", flush=True)
        batch.append(row)
        done.add(_key(c))
        if len(batch) >= 100:
            append_rows(out, batch, fields)
            batch = []
            state["payroll_done"] = sorted(done)
            save_state(state)
        if (i + 1) % 500 == 0:
            print(f"[payroll] {i + 1}/{len(fresh)}", flush=True)
    if batch:
        append_rows(out, batch, fields)
    state["payroll_done"] = sorted(done)
    save_state(state)
    print(f"[payroll] done. rows in {out}", flush=True)


def run_mandate(max_cells: int | None, seeds: int) -> None:
    out = RESULTS / "mandate_sweep.csv"
    fields = ["n_members", "term_blocks", "seed", "n_granted",
              "hhi_concentration", "n_lapsed"]
    state = load_state()
    done = set(state.get("mandate_done", []))
    cells = [
        {"n_members": n, "term_blocks": t, "seed": s}
        for n, t, s in itertools.product(
            [5, 15, 51], [1, 2, 3, 5, 10, 20], range(seeds)
        )
    ]

    def _key(c: dict) -> str:
        return f"{c['n_members']}/{c['term_blocks']}/{c['seed']}"

    print(f"[mandate] {len(cells)} cells, {len(done)} done", flush=True)
    fresh = [c for c in cells if _key(c) not in done]
    if max_cells:
        fresh = fresh[:max_cells]
    batch = []
    for i, c in enumerate(fresh):
        try:
            row = run_mandate_cell(**c)
        except Exception as e:
            row = {**c, "n_granted": -1, "hhi_concentration": -1, "n_lapsed": -1}
            print(f"[mandate] cell failed {c}: {e}", flush=True)
        batch.append(row)
        done.add(_key(c))
        if len(batch) >= 50:
            append_rows(out, batch, fields)
            batch = []
            state["mandate_done"] = sorted(done)
            save_state(state)
        if (i + 1) % 200 == 0:
            print(f"[mandate] {i + 1}/{len(fresh)}", flush=True)
    if batch:
        append_rows(out, batch, fields)
    state["mandate_done"] = sorted(done)
    save_state(state)
    print(f"[mandate] done. rows in {out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", choices=["gov", "payroll", "mandate"], required=True)
    ap.add_argument("--cells", type=int, default=None)
    ap.add_argument("--seeds", type=int,
                    default=int(os.environ.get("SEEDS", "0") or 0) or None)
    args = ap.parse_args()
    defaults = {"gov": 20, "payroll": 30, "mandate": 50}
    seeds = args.seeds or defaults[args.job]
    t0 = time.time()
    print(f"[sweep] job={args.job} seeds={seeds} cells={args.cells or 'all'}",
          flush=True)
    {"gov": run_gov, "payroll": run_payroll, "mandate": run_mandate}[args.job](
        args.cells, seeds
    )
    print(f"[sweep] job={args.job} elapsed={time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
