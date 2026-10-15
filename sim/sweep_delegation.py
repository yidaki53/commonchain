"""Delegation sweep: does it fix turnout, and what does it cost?

This is the experiment that tests the claim night 1 *recommended* but never
tested. The finding was "turnout is the binding constraint, so use gasless and
liquid voting" -- the delegation half of that had no evidence behind it.

The result is allowed to be negative. The literature warns it might be:
Alouf-Heffetz et al. (arXiv:2403.07558) note delegation "results in a power
structure in which certain agents possess more voting weight than others" and
"opens up certain possibilities of vote manipulation". So the sweep measures the
cost alongside the benefit rather than assuming the benefit.
"""

from __future__ import annotations

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

OUT = ROOT / "results" / "night2" / "delegation_sweep.csv"
STATE = ROOT / "results" / "night2" / "delegation_state.json"
FIELDS = [
    "n_members", "apath_frac", "p_abstain", "delegation_rate", "max_depth",
    "seed", "baseline_pass_rate", "delegated_pass_rate",
    "baseline_quorum_fail", "delegated_quorum_fail",
    "max_delegate_share", "delegate_hhi", "effective_voter_frac",
    "cycles", "truncated", "elapsed_s",
]


def run_once(
    n_members: int,
    apath_frac: float,
    p_abstain: float,
    delegation_rate: float,
    max_depth: int,
    seed: int,
    n_proposals: int = 20,
) -> dict:
    rng = random.Random(seed)
    charter = Charter.model_validate(
        {"name": "sim", "mission": "delegation sim", "quorum_pct": 50.0}
    )
    members = [Member(address=f"0x{i:04x}") for i in range(n_members)]
    addrs = [m.address for m in members]

    # Standing delegation map: delegation is a persistent arrangement, not a
    # per-proposal coin flip.
    delegations = dmod.build_delegation_map(addrs, delegation_rate, rng, max_depth)
    res = dmod.resolve_delegations(addrs, delegations, max_depth)
    max_share, hhi = dmod.concentration(addrs, res.resolved)

    def tally(use_delegation: bool) -> tuple[float, float]:
        col = Collective.from_charter(charter, members)
        # Independent stream per arm: reusing one RNG would make the delegated
        # arm see a different random sequence than the baseline purely because
        # it consumes different numbers of draws, which would confound the
        # comparison we are trying to make.
        arm_rng = random.Random(seed * 7919 + (1 if use_delegation else 0))
        apath = set(
            arm_rng.sample(
                addrs, min(int(round(n_members * apath_frac)), n_members)
            )
        )
        passed = qfail = 0
        for i in range(n_proposals):
            abstaining = [
                a for a in addrs
                if a in apath and arm_rng.random() < p_abstain
            ]
            present = [a for a in addrs if a not in abstaining]

            casters: dict[str, bool] = {
                a: (arm_rng.random() < 0.6) for a in present
            }
            if use_delegation:
                # A delegate casts ONE ballot no matter how many members they
                # represent. Two abstainers sharing a delegate must not produce
                # two ballots -- that is weighted voting, which governance.py
                # rejects by design. Representation changes *who* votes, never
                # *how much* a vote weighs.
                carried = {
                    res.resolved[a] for a in abstaining if a in res.resolved
                }
                for caster in carried:
                    casters.setdefault(caster, arm_rng.random() < 0.6)

            ballots = [Ballot(voter=a, yes=v) for a, v in casters.items()]
            block = col.propose(f"p{i}", ballots)
            if block.tally.passed:
                passed += 1
            elif not block.tally.quorum_met:
                qfail += 1
        return passed / n_proposals, qfail / n_proposals

    b_pass, b_qfail = tally(False)
    d_pass, d_qfail = tally(True)
    return {
        "n_members": n_members,
        "apath_frac": apath_frac,
        "p_abstain": p_abstain,
        "delegation_rate": delegation_rate,
        "max_depth": max_depth,
        "seed": seed,
        "baseline_pass_rate": round(b_pass, 4),
        "delegated_pass_rate": round(d_pass, 4),
        "baseline_quorum_fail": round(b_qfail, 4),
        "delegated_quorum_fail": round(d_qfail, 4),
        "max_delegate_share": round(max_share, 4),
        "delegate_hhi": round(hhi, 6),
        "effective_voter_frac": round(res.n_effective_voters / n_members, 4),
        "cycles": res.cycles_detected,
        "truncated": res.chains_truncated,
    }


def grid(seeds: int) -> list[dict]:
    cells = []
    for n, apath, pa, rate, depth in itertools.product(
        [5, 15, 51], [0.3, 0.5, 0.7], [0.8, 0.95], [0.0, 0.25, 0.5], [1, 3]
    ):
        if rate == 0.0 and depth != 1:
            continue  # depth is meaningless without delegation
        for s in range(seeds):
            cells.append({
                "n_members": n, "apath_frac": apath, "p_abstain": pa,
                "delegation_rate": rate, "max_depth": depth, "seed": s,
            })
    return cells


def key(c: dict) -> str:
    return (
        f"{c['n_members']}/{c['apath_frac']}/{c['p_abstain']}/"
        f"{c['delegation_rate']}/{c['max_depth']}/{c['seed']}"
    )


def main() -> None:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cells = grid(seeds)
    done: set[str] = set()
    if STATE.exists():
        done = set(json.loads(STATE.read_text()).get("delegation_done", []))
    fresh = [c for c in cells if key(c) not in done]
    fresh = fresh[: int(sys.argv[2])] if len(sys.argv) > 2 else fresh
    print(f"[deleg] {len(cells)} cells, {len(done)} done, {len(fresh)} fresh",
          flush=True)

    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if OUT.stat().st_size == 0:
            w.writeheader()
        for i, c in enumerate(fresh):
            t0 = time.time()
            try:
                row = run_once(**c)
            except Exception as e:
                print(f"[deleg] cell failed {c}: {e}", flush=True)
                continue
            row["elapsed_s"] = round(time.time() - t0, 3)
            w.writerow(row)
            f.flush()
            done.add(key(c))
            if (i + 1) % 100 == 0:
                STATE.write_text(json.dumps({"delegation_done": sorted(done)}))
                print(f"[deleg] {i + 1}/{len(fresh)}", flush=True)
    STATE.write_text(json.dumps({"delegation_done": sorted(done)}))
    print(f"[deleg] done. rows in {OUT}", flush=True)


if __name__ == "__main__":
    main()
