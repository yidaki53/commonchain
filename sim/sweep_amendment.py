"""Night 5, Job 2: constitutional capture of the amendable policy layer.

``stress.py`` hammers the *immutable* core with unanimous ballots and proves
it can't be amended. Necessary but not sufficient: the amendable policy layer
(supermajority, quorum, pass threshold) is the real attack surface, because
lowering ``supermajority_pct`` is a *legal* amendment -- and once lowered,
every further amendment is legal at the new threshold. That cascade is
constitutional capture.

Experiment: a disciplined hostile bloc repeatedly proposes "lower
supermajority to 50". Honest members show up with probability
``honest_turnout`` per round and vote NO (capture rounds) or YES (recovery
rounds). While uncaptured, each round is a capture attempt; once captured,
each round is an honest recovery attempt. Per cell we record:

  captured_any / n_captures / n_restores
  first_capture / first_restore   (-1 if never)
  final_supermajority, chain_versions
  chain_ok        verify() after every round -- versioned history must hold

The phase space (bloc size x honest turnout x supermajority) connects to
Night 1's headline: the formal supermajority is NOT the binding protection --
turnout is, because ``evaluate`` computes yes-share over *cast* ballots. A 34%
disciplined bloc can pass a 66% supermajority amendment when honest turnout
is low; an honest majority that shows up once recovers. Both directions are
measured, not assumed.

Runs the REAL engine (propose -> evaluate -> _apply_effects -> versioned
charter_history). Isolated state under results/night5/; ``--smoke`` writes
*_smoke files that can never truncate the full grid.
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

RESULTS = ROOT / "results" / "night5"
FIELDS = [
    "n_members", "supermajority_pct", "hostile_frac", "honest_turnout",
    "seed", "n_rounds", "captured_any", "n_captures", "n_restores",
    "first_capture", "first_restore", "final_supermajority",
    "chain_versions", "chain_ok", "elapsed_s",
]

HOLD_TURNOUT = 0.8  # honest turnout during recovery rounds (engaged majority)
CAPTURE_TARGET = 50.0  # what the hostile bloc lowers supermajority to


def run_cell(
    n_members: int,
    supermajority_pct: float,
    hostile_frac: float,
    honest_turnout: float,
    seed: int,
    n_rounds: int = 40,
) -> dict:
    rng = random.Random(seed)
    charter = Charter.model_validate(
        {
            "name": "capture-sim",
            "mission": "constitutional capture experiment",
            "quorum_pct": 50.0,
            "pass_pct": 50.0,
            "supermajority_pct": supermajority_pct,
        }
    )
    members = [Member(address=f"0x{i:04x}") for i in range(n_members)]
    col = Collective.from_charter(charter, members)
    addrs = [m.address for m in col.active_members()]
    n_hostile = max(1, int(round(n_members * hostile_frac)))
    hostile = set(addrs[:n_hostile])
    honest = [a for a in addrs if a not in hostile]

    captured = False
    n_captures = n_restores = 0
    first_capture = first_restore = -1
    chain_ok = True

    for r in range(n_rounds):
        # Honest turnout: per-member Bernoulli each round. While uncaptured it
        # is the cell's honest_turnout; once captured, HOLD_TURNOUT -- an
        # engaged majority re-engaging is what "recovery" means.
        p_show = honest_turnout if not captured else HOLD_TURNOUT
        showing = [a for a in honest if rng.random() < p_show]
        if captured:
            # Honest recovery motion: restore the original supermajority.
            ballots = [Ballot(voter=a, yes=True) for a in showing]
            ballots += [Ballot(voter=a, yes=False) for a in hostile]
            title = f"restore-{r}"
            payload = {"charter": {"supermajority_pct": supermajority_pct}}
        else:
            # Hostile capture motion: legally lower the supermajority.
            ballots = [Ballot(voter=a, yes=True) for a in hostile]
            ballots += [Ballot(voter=a, yes=False) for a in showing]
            title = f"capture-{r}"
            payload = {"charter": {"supermajority_pct": CAPTURE_TARGET}}
        if not ballots:
            continue  # nobody showed: quorum cannot be met anyway
        try:
            block = col.propose(
                title, ballots, kind="charter_amendment", payload=payload
            )
        except Exception:  # noqa: BLE001 - engine rejections are recorded
            continue
        if block.tally.passed:
            if captured:
                n_restores += 1
                if first_restore < 0:
                    first_restore = r
                captured = False
            else:
                n_captures += 1
                if first_capture < 0:
                    first_capture = r
                captured = True
        if not col.verify():
            chain_ok = False
            break

    return {
        "n_members": n_members,
        "supermajority_pct": supermajority_pct,
        "hostile_frac": round(hostile_frac, 3),
        "honest_turnout": round(honest_turnout, 3),
        "seed": seed,
        "n_rounds": n_rounds,
        "captured_any": 1 if first_capture >= 0 else 0,
        "n_captures": n_captures,
        "n_restores": n_restores,
        "first_capture": first_capture,
        "first_restore": first_restore,
        "final_supermajority": col.charter.supermajority_pct,
        "chain_versions": col.charter_version,
        "chain_ok": 1 if chain_ok else 0,
    }


def _key(c: dict) -> str:
    return "/".join(
        f"{c[k]}" for k in (
            "n_members", "supermajority_pct", "hostile_frac",
            "honest_turnout", "seed",
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    suffix = "_smoke" if args.smoke else ""
    out = RESULTS / f"amendment_sweep{suffix}.csv"
    state_file = RESULTS / f"amendment_state{suffix}.json"

    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    done = set(state.get("done", []))
    seeds = 2 if args.smoke else args.seeds
    n_rounds = 8 if args.smoke else 40
    ns = (15,) if args.smoke else (15, 51)
    supers = (66.0,) if args.smoke else (60.0, 66.0, 75.0)
    fracs = (0.34,) if args.smoke else (0.2, 0.3, 0.34, 0.4, 0.5)
    turns = (0.5,) if args.smoke else (0.2, 0.5, 0.8)

    grid = [
        {"n_members": n, "supermajority_pct": s, "hostile_frac": h,
         "honest_turnout": t, "seed": seed}
        for n, s, h, t, seed in itertools.product(
            ns, supers, fracs, turns, range(seeds),
        )
    ]
    fresh = [c for c in grid if _key(c) not in done]
    print(f"[capture] {len(grid)} cells total, {len(done)} done, "
          f"{len(fresh)} fresh", flush=True)

    new_file = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, c in enumerate(fresh):
            t0 = time.time()
            try:
                row = run_cell(**c, n_rounds=n_rounds)
            except Exception as e:  # noqa: BLE001 - failed cells recorded
                print(f"[capture] FAILED {c}: {e}", flush=True)
                row = {k: (-1 if k not in c else c[k]) for k in FIELDS
                       if k != "elapsed_s"}
            row["elapsed_s"] = round(time.time() - t0, 3)
            w.writerow({k: row.get(k) for k in FIELDS})
            f.flush()
            done.add(_key(c))
            state["done"] = sorted(done)
            state_file.write_text(json.dumps(state))
            if (i + 1) % 250 == 0:
                print(f"[capture] {i + 1}/{len(fresh)} fresh cells done",
                      flush=True)
    print(f"[capture] complete -> {out}", flush=True)


if __name__ == "__main__":
    main()
