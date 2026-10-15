"""Night 3, Job 3: ballot / choice fuzz + hash-round-trip determinism.

Two properties checked over randomized inputs:
1. evaluate() accepts or rejects with ValueError -- never any other exception.
   A tallying crash would take a collective's decision night down.
2. Hash determinism for identical inputs, stability across a JSON round-trip,
   and tamper detection by verify().

Note on timestamps: Charter/Member/Proposal stamp wall-clock time via
``default_factory=time.time`` (bound at import, so no clock mock can freeze
it). Identical *logical* inputs proposed a millisecond apart are therefore
correctly different blocks. The determinism check pins every timestamp
explicitly, so "identical inputs -> identical hash" is tested honestly.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective  # noqa: E402
from commonchain.governance import Ballot, Proposal, evaluate  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

T0 = 1_792_000_000.0  # pinned timestamp: every stamped field gets this


def _det_charter() -> Charter:
    return Charter.model_validate(
        {
            "name": "det",
            "mission": "m",
            "voting_rule": "plurality",
            "quorum_pct": 50.0,
            "created_at": T0,
        }
    )


def _det_members() -> list[Member]:
    return [Member(address=f"0x{j:03x}", joined_at=T0) for j in range(5)]


def _det_proposal() -> Proposal:
    return Proposal(title="det-1", options=["yes", "no"], created_at=T0)


def _det_ballots() -> list[Ballot]:
    return [Ballot(voter="0x000", yes=True), Ballot(voter="0x001", yes=False)]


def main(iterations: int = 2000, seed: int = 11) -> None:
    rng = random.Random(seed)
    rules = ("binary", "plurality", "approval")
    accepted = rejected = 0

    for _ in range(iterations):
        rule = rng.choice(rules)
        n = rng.randint(1, 12)
        charter = Charter.model_validate(
            {
                "name": "fuzz",
                "mission": "f",
                "voting_rule": rule,
                "quorum_pct": rng.choice([0.0, 50.0, 100.0]),
            }
        )
        members = [Member(address=f"0x{j:03x}") for j in range(n)]
        n_opts = rng.randint(0, 4)
        options = [f"o{j}" for j in range(n_opts)]
        proposal = Proposal(title="fuzz", options=options)
        ballots = []
        for _ in range(rng.randint(0, n + 2)):  # sometimes over-votes membership
            voter = f"0x{rng.randrange(n + 2):03x}"
            k = rng.randint(0, 3)
            chs = [rng.choice(options) if options else "yes" for _ in range(k)]
            try:
                ballots.append(Ballot(voter=voter, choices=chs))
            except ValueError:
                pass  # empty/dup choices: already rejected at construction
        try:
            evaluate(charter, members, proposal, ballots)
            accepted += 1
        except ValueError:
            rejected += 1
        except Exception as e:  # noqa: BLE001
            raise AssertionError(
                f"unexpected {type(e).__name__} for {rule} at iter {_}",
                f"{e!r}",
            ) from e

    # Identical inputs must give identical hashes. propose() stamps the wall
    # clock, so drive the same path it drives (evaluate + _append) with every
    # timestamp pinned, on two independent collectives.
    col = Collective.from_charter(_det_charter(), _det_members())
    col2 = Collective.from_charter(_det_charter(), _det_members())
    b1 = col._append(  # noqa: SLF001 - same call propose() makes internally
        evaluate(col.charter, col.active_members(), _det_proposal(), _det_ballots())
    )
    b2 = col2._append(  # noqa: SLF001
        evaluate(col2.charter, col2.active_members(), _det_proposal(), _det_ballots())
    )
    assert b1.block_hash == b2.block_hash, "identical inputs must give identical hash"

    # Hash stability across a JSON round-trip.
    dumped = json.loads(b1.model_dump_json())
    reloaded = type(b1).model_validate(dumped)
    assert reloaded.compute_hash() == b1.block_hash, "hash changed across JSON round-trip"
    assert col.verify(), "chain broken after round-trip"

    # Tamper with the live chain: verify() must catch it, then restore.
    saved_voter = b1.tally.ballots[0].voter
    b1.tally.ballots[0].voter = "0xfff"
    assert b1.compute_hash() != b1.block_hash, "tamper did not change the hash"
    assert not col.verify(), "verify() missed a tampered ballot"
    b1.tally.ballots[0].voter = saved_voter
    assert col.verify(), "chain broken after restoring tampered ballot"

    print(f"[ballot_fuzz] accepted={accepted} rejected={rejected} (all ValueError)", flush=True)
    print("[ballot_fuzz] HASH DETERMINISM + ROUND-TRIP + TAMPER DETECTION OK", flush=True)


if __name__ == "__main__":
    main()
