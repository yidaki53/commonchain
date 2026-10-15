"""Night 3, Job 1: voting-rule sweep (binary vs plurality vs approval).

Club-scale collectives (N in {5, 9, 15, 30}) decide multi-option proposals
under sincere preferences with an apathy abstention model. Runs the REAL
engine (Collective.propose + evaluate): no reimplementation of tallying.

Isolated state under results/night3/ so a smoke test can never truncate the
full grid (night-1 lesson). `--smoke` writes voting_smoke* files instead.

Metrics per cell:
  pass_rate           decided / proposals (binary: yes-share + quorum;
                      plurality/approval: unique leader + quorum)
  tie_rate            plurality/approval ties (recorded, never broken)
  minority_win_rate   decided proposals whose winner had <50% of ballots cast
  mean_turnout        ballots cast / eligible, per proposal
  mean_winner_share   winner share among decided (binary: yes share)
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective  # noqa: E402
from commonchain.governance import Ballot  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

RESULTS = ROOT / "results" / "night3"
FIELDS = [
    "voting_rule", "n_members", "p_abstain", "seed", "n_proposals",
    "pass_rate", "tie_rate", "minority_win_rate", "mean_turnout",
    "mean_winner_share", "elapsed_s",
]


def run_voting_cell(
    voting_rule: str,
    n_members: int,
    p_abstain: float,
    seed: int,
    n_proposals: int = 20,
    n_options: int = 3,
) -> dict:
    rng = random.Random(seed)
    charter = Charter.model_validate(
        {
            "name": "voting-sim",
            "mission": "voting rule simulation",
            "kind": "club",
            "voting_rule": voting_rule,
            "quorum_pct": 50.0,
            "pass_pct": 50.0,
        }
    )
    members = [Member(address=f"0x{i:04x}") for i in range(n_members)]
    col = Collective.from_charter(charter, members)
    addrs = [m.address for m in col.active_members()]

    n_decided = n_tie = n_minority = 0
    turnout_sum = share_sum = 0.0
    for p in range(n_proposals):
        options = [f"opt{j}" for j in range(n_options)]
        prefs = list(options)
        rng.shuffle(prefs)
        favorite, last = prefs[0], prefs[-1]
        ballots = []
        for a in addrs:
            if rng.random() < p_abstain:
                continue
            if voting_rule == "binary":
                ballots.append(Ballot(voter=a, yes=(rng.random() < 0.6)))
            elif voting_rule == "plurality":
                ballots.append(Ballot(voter=a, choices=[favorite]))
            else:  # approval: favorite always, last option sometimes
                chs = [favorite] + ([last] if rng.random() < 0.5 else [])
                ballots.append(Ballot(voter=a, choices=chs))
        turnout_sum += len(ballots)
        block = col.propose(
            f"p{p}",
            ballots,
            options=[] if voting_rule == "binary" else options,
        )
        t = block.tally
        if t.passed:
            n_decided += 1
            share = (
                t.yes / len(ballots) * 100.0
                if voting_rule == "binary"
                else t.winner_share_pct
            )
            share_sum += share
            if share < 50.0:
                n_minority += 1
        elif t.tie:
            n_tie += 1

    n_all = n_members * n_proposals
    return {
        "voting_rule": voting_rule,
        "n_members": n_members,
        "p_abstain": p_abstain,
        "seed": seed,
        "n_proposals": n_proposals,
        "pass_rate": n_decided / n_proposals,
        "tie_rate": n_tie / n_proposals,
        "minority_win_rate": (n_minority / n_decided) if n_decided else 0.0,
        "mean_turnout": turnout_sum / n_all if n_all else 0.0,
        "mean_winner_share": (share_sum / n_decided) if n_decided else 0.0,
    }


def _key(c: dict) -> str:
    return f"{c['voting_rule']}/{c['n_members']}/{c['p_abstain']}/{c['seed']}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="tiny run against ISOLATED smoke state/csv (safe preflight)",
    )
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    suffix = "_smoke" if args.smoke else ""
    out = RESULTS / f"voting_sweep{suffix}.csv"
    state_file = RESULTS / f"voting_state{suffix}.json"

    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    done = set(state.get("done", []))
    seeds = 2 if args.smoke else args.seeds
    grid = [
        {"voting_rule": r, "n_members": n, "p_abstain": pa, "seed": s}
        for r, n, pa, s in itertools.product(
            ("binary", "plurality", "approval"),
            (5, 9, 15, 30),
            (0.0, 0.5, 0.8, 0.95),
            range(seeds),
        )
    ]
    fresh = [c for c in grid if _key(c) not in done]
    print(
        f"[voting] {len(grid)} cells total, {len(done)} done, {len(fresh)} fresh",
        flush=True,
    )

    new_file = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, c in enumerate(fresh):
            t0 = time.time()
            try:
                row = run_voting_cell(**c)
            except Exception as e:  # noqa: BLE001 - failed cells are recorded
                print(f"[voting] FAILED {c}: {e}", flush=True)
                row = {
                    k: (-1 if k not in c else c[k])
                    for k in FIELDS
                    if k != "elapsed_s"
                }
            row["elapsed_s"] = round(time.time() - t0, 3)
            w.writerow({k: row.get(k) for k in FIELDS})
            f.flush()
            done.add(_key(c))
            state["done"] = sorted(done)
            state_file.write_text(json.dumps(state))
            if (i + 1) % 100 == 0:
                print(f"[voting] {i + 1}/{len(fresh)} fresh cells done", flush=True)
    print(f"[voting] complete -> {out}", flush=True)


if __name__ == "__main__":
    main()
