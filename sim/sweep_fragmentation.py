"""Night 5, Job 1: voting rules under fragmented preferences.

Night 3's voting sweep drew each member's favorite uniformly at random. That
makes preferences *noise* rather than *faction*: no coherent minority exists,
so ``minority_win_rate`` was ~0 by construction and the table flagged it. This
sweep models blocs instead, so minority winners can genuinely occur, and asks
what each rule does with them:

* ``plurality``  -- expected to elect minority-bloc favorites whenever the
  majority is split across >=2 blocs (the classic coordination failure);
* ``approval``   -- expected to elect consensus options that nobody hates;
* ``binary``     -- cannot produce a minority winner at all (pass requires
  >=50% of cast ballots) but pays in deadlocks when no majority favorite
  is on the agenda.

Bloc model: members partition into ``n_blocs`` coherent blocs; bloc j's
favorite is option j. Bloc 0 is the *targeted minority* with share
``minority_frac``; the rest split evenly. Each member ranks their own bloc's
option first unless cross-pressured (probability ``p_noise``), in which case
their ranking is a seeded random permutation.

Binary arm: the agenda offers the favorite of the *largest* bloc as a yes/no
motion. ``minority_win_rate`` is 0 under binary by construction -- that is the
citable contrast, not a modelling accident.

Runs the REAL engine (Collective.propose + evaluate). Isolated state under
results/night5/ (night-1 lesson); ``--smoke`` writes *_smoke files that can
never truncate the full grid.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective  # noqa: E402
from commonchain.governance import Ballot  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

RESULTS = ROOT / "results" / "night5"
FIELDS = [
    "voting_rule", "n_blocs", "minority_frac", "p_noise", "p_abstain",
    "n_members", "seed", "n_proposals", "pass_rate", "tie_rate",
    "minority_win_rate", "mean_turnout", "mean_winner_share",
    "mean_satisfaction", "coherence_rate", "elapsed_s",
]


def bloc_sizes(n_members: int, n_blocs: int, minority_frac: float) -> list[int]:
    """Bloc 0 gets the minority share; the rest split evenly (deterministic)."""
    size0 = max(1, int(round(n_members * minority_frac)))
    size0 = min(size0, n_members - (n_blocs - 1))  # leave >=1 for each other
    rest = n_members - size0
    base, extra = divmod(rest, n_blocs - 1)
    return [size0] + [base + (1 if j < extra else 0) for j in range(n_blocs - 1)]


def run_cell(
    voting_rule: str,
    n_blocs: int,
    minority_frac: float,
    p_noise: float,
    p_abstain: float,
    n_members: int,
    seed: int,
    n_proposals: int = 30,
) -> dict:
    rng = random.Random(seed)
    charter = Charter.model_validate(
        {
            "name": "fragmentation-sim",
            "mission": "voting rules under fragmented preferences",
            "kind": "club",
            "voting_rule": voting_rule,
            "quorum_pct": 50.0,
            "pass_pct": 50.0,
        }
    )
    members = [Member(address=f"0x{i:04x}") for i in range(n_members)]
    col = Collective.from_charter(charter, members)
    addrs = [m.address for m in col.active_members()]

    # Deterministic bloc assignment: members 0..size0-1 in bloc 0, etc.
    sizes = bloc_sizes(n_members, n_blocs, minority_frac)
    bloc_of: dict[str, int] = {}
    idx = 0
    for j, sz in enumerate(sizes):
        for _ in range(sz):
            bloc_of[addrs[idx]] = j
            idx += 1
    majority_bloc = max(range(n_blocs), key=lambda j: (sizes[j], -j))
    options = [f"opt{j}" for j in range(n_blocs)]

    n_decided = n_tie = n_minority = n_coherent = 0
    turnout_sum = share_sum = sat_sum = 0.0
    for _p in range(n_proposals):
        # Preference profile: own-bloc favorite first unless cross-pressured.
        rankings: dict[str, list[str]] = {}
        for a in addrs:
            opts = list(options)
            if rng.random() < p_noise:
                rng.shuffle(opts)  # cross-pressured: arbitrary ordering
            else:
                fav = f"opt{bloc_of[a]}"
                opts.remove(fav)
                rng.shuffle(opts)
                opts.insert(0, fav)
            rankings[a] = opts

        ballots = []
        for a in addrs:
            if rng.random() < p_abstain:
                continue
            top = rankings[a][0]
            if voting_rule == "binary":
                agenda = f"opt{majority_bloc}"
                ballots.append(Ballot(voter=a, yes=(top == agenda)))
            elif voting_rule == "plurality":
                ballots.append(Ballot(voter=a, choices=[top]))
            else:  # approval: top half of the ranking
                k = max(1, math.ceil(len(options) / 2))
                ballots.append(Ballot(voter=a, choices=rankings[a][:k]))

        cast = len(ballots)
        turnout_sum += cast
        block = col.propose(
            "motion", ballots,
            options=[] if voting_rule == "binary" else options,
        )
        t = block.tally
        if t.passed:
            n_decided += 1
            if voting_rule == "binary":
                share = t.yes / cast * 100.0
                # Ballots from the bloc whose favorite is the agenda motion.
                maj_ballots = sum(
                    1 for b in ballots if bloc_of[b.voter] == majority_bloc
                )
                sat_sum += maj_ballots / cast
                coherent = share > 50.0
            else:
                winner = t.winner
                share = t.winner_share_pct
                sat_sum += sum(
                    1 for b in ballots if winner in b.choices
                ) / cast
                appr = sum(1 for b in ballots if winner in b.choices)
                coherent = appr / cast > 0.5
                wbloc = int(winner.replace("opt", ""))
                bloc_cast = sum(
                    1 for b in ballots if bloc_of[b.voter] == wbloc
                )
                if bloc_cast / cast < 0.5:
                    n_minority += 1
            share_sum += share
            n_coherent += 1 if coherent else 0
        elif t.tie:
            n_tie += 1

    n_all = n_members * n_proposals
    return {
        "voting_rule": voting_rule,
        "n_blocs": n_blocs,
        "minority_frac": round(minority_frac, 3),
        "p_noise": round(p_noise, 3),
        "p_abstain": round(p_abstain, 3),
        "n_members": n_members,
        "seed": seed,
        "n_proposals": n_proposals,
        "pass_rate": round(n_decided / n_proposals, 4),
        "tie_rate": round(n_tie / n_proposals, 4),
        "minority_win_rate": round(
            (n_minority / n_decided) if n_decided else 0.0, 4
        ),
        "mean_turnout": round(turnout_sum / n_all if n_all else 0.0, 4),
        "mean_winner_share": round(
            (share_sum / n_decided) if n_decided else 0.0, 4
        ),
        "mean_satisfaction": round(
            (sat_sum / n_decided) if n_decided else 0.0, 4
        ),
        "coherence_rate": round(
            (n_coherent / n_decided) if n_decided else 0.0, 4
        ),
    }


def _key(c: dict) -> str:
    return "/".join(
        f"{c[k]}" for k in (
            "voting_rule", "n_blocs", "minority_frac", "p_noise",
            "p_abstain", "n_members", "seed",
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    suffix = "_smoke" if args.smoke else ""
    out = RESULTS / f"fragmentation_sweep{suffix}.csv"
    state_file = RESULTS / f"fragmentation_state{suffix}.json"

    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    done = set(state.get("done", []))
    seeds = 2 if args.smoke else args.seeds
    n_props = 6 if args.smoke else 30
    nb = (2, 3) if args.smoke else (2, 3, 5)
    mf = (0.2,) if args.smoke else (0.2, 0.35)
    noise = (0.0, 0.8) if args.smoke else (0.0, 0.4, 0.8)
    pa = (0.5,) if args.smoke else (0.0, 0.5, 0.8)
    ns = (9,) if args.smoke else (9, 30)

    grid = [
        {"voting_rule": r, "n_blocs": k, "minority_frac": m, "p_noise": nz,
         "p_abstain": p, "n_members": n, "seed": s}
        for r, k, m, nz, p, n, s in itertools.product(
            ("binary", "plurality", "approval"), nb, mf, noise, pa, ns,
            range(seeds),
        )
    ]
    fresh = [c for c in grid if _key(c) not in done]
    print(f"[frag] {len(grid)} cells total, {len(done)} done, "
          f"{len(fresh)} fresh", flush=True)

    new_file = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, c in enumerate(fresh):
            t0 = time.time()
            try:
                row = run_cell(**c, n_proposals=n_props)
            except Exception as e:  # noqa: BLE001 - failed cells are recorded
                print(f"[frag] FAILED {c}: {e}", flush=True)
                row = {k: (-1 if k not in c else c[k]) for k in FIELDS
                       if k != "elapsed_s"}
            row["elapsed_s"] = round(time.time() - t0, 3)
            w.writerow({k: row.get(k) for k in FIELDS})
            f.flush()
            done.add(_key(c))
            state["done"] = sorted(done)
            state_file.write_text(json.dumps(state))
            if (i + 1) % 250 == 0:
                print(f"[frag] {i + 1}/{len(fresh)} fresh cells done",
                      flush=True)
    print(f"[frag] complete -> {out}", flush=True)


if __name__ == "__main__":
    main()

