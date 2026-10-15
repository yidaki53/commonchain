"""Chain stress + integrity fuzz (Job 4). Appends 50k blocks, times hot paths,
flips stored data to confirm verify() catches 100%, and hammers random
charter amendments to prove the immutable core never changes.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective, GovernanceError  # noqa: E402
from commonchain.governance import Ballot  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def main(n_blocks: int = 50000, n_fuzz: int = 1000, n_amend: int = 5000) -> None:
    log = RESULTS / "stress.log"
    out: list[str] = []

    def emit(s: str) -> None:
        print(s, flush=True)
        out.append(s)

    charter = Charter.model_validate(
        {"name": "stress", "mission": "stress test", "quorum_pct": 30.0}
    )
    members = [Member(address=f"0x{i:04x}") for i in range(9)]
    col = Collective.from_charter(charter, members)
    addrs = [m.address for m in members]

    t0 = time.time()
    for i in range(n_blocks):
        voters = addrs[:5]
        col.propose(f"b{i}", [Ballot(voter=a, yes=(i % 2 == 0)) for a in voters])
    t_propose = time.time() - t0
    emit(f"appended {n_blocks} blocks in {t_propose:.1f}s "
         f"({n_blocks / t_propose:.0f} blocks/s)")

    t0 = time.time()
    ok = col.verify()
    t_verify = time.time() - t0
    emit(f"verify() over {n_blocks} blocks: {ok} in {t_verify:.1f}s")

    t0 = time.time()
    trail = col.audit_trail()
    emit(f"audit_trail() over {len(trail)} blocks in {time.time() - t0:.1f}s")

    # Fuzz: mutate stored ballots/hashes, verify() must catch every one.
    rng = random.Random(42)
    caught = 0
    for _ in range(n_fuzz):
        b = rng.choice(col.chain)
        saved_yes, saved_hash = b.tally.yes, b.block_hash
        if rng.random() < 0.5:
            b.tally.yes = saved_yes + 99
        else:
            b.block_hash = "ff" * 32
        if not col.verify():
            caught += 1
        b.tally.yes, b.block_hash = saved_yes, saved_hash
    emit(f"tamper fuzz: {caught}/{n_fuzz} caught")
    assert caught == n_fuzz, "verify() missed a tamper!"

    # Amendment hammer: random policy changes must never touch the core.
    col2 = Collective.from_charter(charter, members)
    ballots = [Ballot(voter=a, yes=True) for a in addrs]
    fields = ["quorum_pct", "pass_pct", "supermajority_pct",
              "modules.payroll.policy", "one_member_one_vote",
              "stakes_transferable"]
    blocked = 0
    for i in range(n_amend):
        f = rng.choice(fields)
        val = rng.choice([True, False, 10.0, 90.0, "equal"])
        try:
            col2.propose(f"amend-{i}", ballots, kind="charter_amendment",
                         payload={"charter": {f: val}})
        except (GovernanceError, ValueError):
            blocked += 1
    emit(f"amendment hammer: {n_amend} attempts, {blocked} rejected; "
         f"core intact: one_member_one_vote={col2.charter.one_member_one_vote}, "
         f"stakes_transferable={col2.charter.stakes_transferable}")
    assert col2.charter.one_member_one_vote is True
    assert col2.charter.stakes_transferable is False
    assert col2.verify()
    emit("ALL STRESS CHECKS PASSED")
    log.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=50000)
    ap.add_argument("--fuzz", type=int, default=1000)
    ap.add_argument("--amend", type=int, default=5000)
    args = ap.parse_args()
    main(args.blocks, args.fuzz, args.amend)
