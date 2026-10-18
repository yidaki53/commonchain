"""Night 5, Job 3: preference-aligned vs random delegation.

Night 2's delegation sweep answered "does liquid democracy fix turnout, and
what does it cost?" -- but its ``build_delegation_map`` assigns delegates
*uniformly at random*. Real liquid democracy lets members *choose* who carries
their proxy. That choice is the load-bearing difference: a member who
delegates within their own bloc (shared preferences) never has their ballot
re-cast against its intent; a random proxy can.

This sweep adds ``aligned_frac``: the probability a delegator picks a delegate
from their own bloc (0.0 = night-2's random model, 1.0 = pure in-bloc choice).

* fidelity       fraction of carried (resolved) ballots whose delegate shares
                 the delegator's bloc -- the representation guarantee;
* pass/quorum deltas vs a paired no-delegation baseline (independent RNG
  streams, night-2's convention);
* max_delegate_share / delegate_hhi -- the concentration cost, measured not
  assumed away (Alouf-Heffetz et al.: delegation "opens up ... vote
  manipulation").

Bloc structure: bloc 0 is a 15% minority voting NO; the rest form the
majority bloc voting YES on a binary motion -- so a carried ballot that
crosses the bloc boundary *flips intent*, which is what fidelity measures.
Delegate weight stays pinned to 1 (module invariant).

Runs the REAL engine. Isolated state under results/night5/; ``--smoke``
writes *_smoke files that can never truncate the full grid.
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
from commonchain.modules import delegation as dmod  # noqa: E402

RESULTS = ROOT / "results" / "night5"
FIELDS = [
    "n_members", "p_abstain", "delegation_rate", "aligned_frac", "max_depth",
    "seed", "baseline_pass", "deleg_pass", "baseline_qfail", "deleg_qfail",
    "fidelity", "n_carried", "max_delegate_share", "delegate_hhi",
    "effective_voter_frac", "cycles", "truncated", "elapsed_s",
]

N_BLOC0 = 0.15  # minority share voting NO


def run_cell(
    n_members: int,
    p_abstain: float,
    delegation_rate: float,
    aligned_frac: float,
    max_depth: int,
    seed: int,
    n_proposals: int = 20,
) -> dict:
    rng = random.Random(seed)
    charter = Charter.model_validate(
        {
            "name": "delegbloc-sim",
            "mission": "aligned delegation experiment",
            "quorum_pct": 50.0,
        }
    )
    members = [Member(address=f"0x{i:04x}") for i in range(n_members)]
    col = Collective.from_charter(charter, members)
    addrs = [m.address for m in col.active_members()]
    n0 = max(1, int(round(n_members * N_BLOC0)))
    bloc0 = set(addrs[:n0])  # minority: sincere NO
    bloc_of = {a: (0 if a in bloc0 else 1) for a in addrs}

    # Standing, aligned-aware delegation map (persistent proxy, chosen once).
    delegations: dict[str, str] = {}
    for a in addrs:
        if rng.random() >= delegation_rate:
            continue
        same = [b for b in addrs if bloc_of[b] == bloc_of[a] and b != a]
        other = [b for b in addrs if bloc_of[b] != bloc_of[a]]
        pool = same if (rng.random() < aligned_frac and same) else (
            other or same
        )
        if pool:
            delegations[a] = rng.choice(pool)
    res = dmod.resolve_delegations(addrs, delegations, max_depth)
    max_share, hhi = dmod.concentration(addrs, res.resolved)
    # Fidelity: carried ballots whose delegate shares the delegator's bloc.
    # Delegations that never resolved (cycles/truncation) fall back to
    # self-voting in the module, so they carry no distortion and are NOT
    # counted here; empty carried -> -1 sentinel ("undefined"), which the
    # CI machinery excludes rather than misreading as perfect fidelity.
    carried = list(res.resolved.items())
    fidelity = (
        sum(1 for s, d in carried if bloc_of[s] == bloc_of[d]) / len(carried)
        if carried else -1.0
    )

    def tally(use_delegation: bool) -> tuple[float, float]:
        c = Collective.from_charter(charter, members)
        # Independent stream per arm (night-2 convention): reusing one RNG
        # would confound the comparison via different draw counts.
        arm_rng = random.Random(seed * 7919 + (1 if use_delegation else 0))
        passed = qfail = 0
        for _ in range(n_proposals):
            present = [a for a in addrs if arm_rng.random() >= p_abstain]
            # Sincere intent: bloc 0 votes NO, everyone else YES.
            casters = {a: (bloc_of[a] == 1) for a in present}
            if use_delegation:
                carried_casters = {
                    res.resolved[a] for a in addrs
                    if a not in present and a in res.resolved
                }
                for caster in carried_casters:
                    casters.setdefault(caster, bloc_of[caster] == 1)
            if not casters:
                qfail += 1
                continue
            ballots = [Ballot(voter=a, yes=v) for a, v in casters.items()]
            block = c.propose("motion", ballots)
            if block.tally.passed:
                passed += 1
            elif not block.tally.quorum_met:
                qfail += 1
        return passed / n_proposals, qfail / n_proposals

    b_pass, b_qfail = tally(False)
    d_pass, d_qfail = tally(True)
    return {
        "n_members": n_members,
        "p_abstain": round(p_abstain, 3),
        "delegation_rate": round(delegation_rate, 3),
        "aligned_frac": round(aligned_frac, 3),
        "max_depth": max_depth,
        "seed": seed,
        "baseline_pass": round(b_pass, 4),
        "deleg_pass": round(d_pass, 4),
        "baseline_qfail": round(b_qfail, 4),
        "deleg_qfail": round(d_qfail, 4),
        "fidelity": round(fidelity, 4),
        "n_carried": len(carried),
        "max_delegate_share": round(max_share, 4),
        "delegate_hhi": round(hhi, 6),
        "effective_voter_frac": round(res.n_effective_voters / n_members, 4),
        "cycles": res.cycles_detected,
        "truncated": res.chains_truncated,
    }


def _key(c: dict) -> str:
    return "/".join(
        f"{c[k]}" for k in (
            "n_members", "p_abstain", "delegation_rate", "aligned_frac",
            "max_depth", "seed",
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    suffix = "_smoke" if args.smoke else ""
    out = RESULTS / f"deleg_blocs_sweep{suffix}.csv"
    state_file = RESULTS / f"deleg_blocs_state{suffix}.json"

    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    done = set(state.get("done", []))
    seeds = 2 if args.smoke else args.seeds
    ns = (30,) if args.smoke else (30,)
    pa = (0.8,) if args.smoke else (0.5, 0.8, 0.95)
    rates = (0.5,) if args.smoke else (0.25, 0.5, 0.75)
    aligns = (0.0, 1.0) if args.smoke else (0.0, 0.5, 1.0)
    depths = (1, 3) if args.smoke else (1, 3)

    grid = [
        {"n_members": n, "p_abstain": p, "delegation_rate": r,
         "aligned_frac": a, "max_depth": d, "seed": s}
        for n, p, r, a, d, s in itertools.product(ns, pa, rates, aligns,
                                                  depths, range(seeds))
    ]
    fresh = [c for c in grid if _key(c) not in done]
    print(f"[delebloc] {len(grid)} cells total, {len(done)} done, "
          f"{len(fresh)} fresh", flush=True)

    new_file = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, c in enumerate(fresh):
            t0 = time.time()
            try:
                row = run_cell(**c)
            except Exception as e:  # noqa: BLE001 - failed cells recorded
                print(f"[delebloc] FAILED {c}: {e}", flush=True)
                row = {k: (-1 if k not in c else c[k]) for k in FIELDS
                       if k != "elapsed_s"}
            row["elapsed_s"] = round(time.time() - t0, 3)
            w.writerow({k: row.get(k) for k in FIELDS})
            f.flush()
            done.add(_key(c))
            state["done"] = sorted(done)
            state_file.write_text(json.dumps(state))
            if (i + 1) % 100 == 0:
                print(f"[delebloc] {i + 1}/{len(fresh)} fresh cells done",
                      flush=True)
    print(f"[delebloc] complete -> {out}", flush=True)


if __name__ == "__main__":
    main()
