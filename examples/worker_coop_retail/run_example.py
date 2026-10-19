#!/usr/bin/env python3
"""Red Rose Worker Co-op Retail — Worker-owned chain on commonchain.

Demonstrates commonchain as a worker cooperative: one worker one vote,
soulbound memberships (non-transferable stakes), equal payroll policy,
and profit sharing — all vote-gated and hash-linked.

Run with: uv run python examples/worker_coop_retail/run_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml  # noqa: E402

from commonchain.chain import Collective, GovernanceError  # noqa: E402
from commonchain.governance import Ballot  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402


def load_charter(path: Path) -> Charter:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Charter.model_validate(data)


def load_members(path: Path) -> list[Member]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Member.model_validate(m) for m in data]


def yes(*addrs: str) -> list[Ballot]:
    return [Ballot(voter=a, yes=True) for a in addrs]


def no(*addrs: str) -> list[Ballot]:
    return [Ballot(voter=a, yes=False) for a in addrs]


def main() -> int:
    root = Path(__file__).resolve().parent
    charter = load_charter(root / "charter.yaml")
    members = load_members(root / "members.yaml")

    collective = Collective.from_charter(charter, members)
    print(f"Genesis hash: {collective.genesis_hash}")
    print(f"Worker-owners: {len(collective.members)}")
    print(f"Charter: {collective.charter.name}")
    print(f"Payroll policy: {collective.charter.modules['payroll']['policy']}")
    print()

    addrs = [m.address for m in members]

    # --- Scenario 1: Extend store hours (binary yes/no vote)
    print("=== Scenario 1: Extend store hours to 9 PM ===")
    block = collective.propose(
        "Extend store hours to 9 PM",
        yes(addrs[0], addrs[1], addrs[2]),
        kind="general",
        payload={"policy_domain": "store_hours", "new_close": "21:00"},
    )
    print(f"  Block {block.index}: passed={block.tally.passed}, "
          f"yes={block.tally.yes}, no={block.tally.no}")
    assert block.tally.passed is True
    print("  PASSED — 3 of 4 workers in favor (75% >= 50% pass threshold).")
    print()

    # --- Scenario 2: Soulbound stake transfer is forbidden
    print("=== Scenario 2: Attempt to transfer soulbound stake ===")
    try:
        # The charter has stakes_transferable=false, enforced by the
        # Charter model validator — any attempt to make it true is rejected
        # at validation time, not at vote time.
        bad = Charter.model_validate({
            **collective.charter.model_dump(mode="json"),
            "stakes_transferable": True,
        })
        print("  ERROR: Charter should have rejected transferable stakes")
        return 1
    except ValueError as e:
        print(f"  REJECTED — {e}")
    print()

    # --- Scenario 3: Non-worker cannot vote
    print("=== Scenario 3: Non-worker attempts to vote ===")
    try:
        collective.propose(
            "Customer discount day",
            [Ballot(voter="0xcustomer", yes=True)],
            kind="general",
        )
        print("  ERROR: Non-member should have been rejected")
        return 1
    except ValueError as e:
        print(f"  REJECTED — {e}")
    print()

    # --- Scenario 4: Profit distribution proposal
    print("=== Scenario 4: Quarterly profit distribution ===")
    block = collective.propose(
        "Distribute Q3 profits equally among worker-owners",
        yes(addrs[0], addrs[1], addrs[2], addrs[3]),
        kind="payroll",
        payload={"module": "profit_sharing", "worker_share_pct": 80.0},
    )
    print(f"  Block {block.index}: passed={block.tally.passed}, "
          f"yes={block.tally.yes}, no={block.tally.no}")
    assert block.tally.passed is True
    print("  PASSED — unanimous worker-owner approval.")
    print()

    # --- Scenario 5: Deactivate a departing worker (offboarding burns stake)
    print("=== Scenario 5: Worker leaves — stake is burned, not transferred ===")
    collective.deactivate_member(addrs[3])
    assert collective.members[addrs[3]].active is False
    print(f"  Worker {addrs[3]} deactivated; stake burned (not transferred).")
    # The departed worker can no longer vote
    try:
        collective.propose(
            "Post-exit vote",
            [Ballot(voter=addrs[3], yes=True)],
            kind="general",
        )
        print("  ERROR: Deactivated member should not be able to vote")
        return 1
    except ValueError as e:
        print(f"  REJECTED — {e}")
    print()

    # --- Scenario 6: Chain integrity
    print("=== Scenario 6: Chain integrity verification ===")
    assert collective.verify() is True
    for i in range(len(collective.chain)):
        assert collective.verify_block(i) is True
    print(f"  Chain verified: {len(collective.chain)} blocks, all hashes valid.")
    print()

    # --- Audit trail
    print("=== Audit trail ===")
    for entry in collective.audit_trail():
        status = "PASSED" if entry["passed"] else "REJECTED"
        print(f"  Block {entry['index']}: {entry['title'][:50]}... [{status}]")
    print()

    print("All Red Rose Worker Co-op scenarios complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())