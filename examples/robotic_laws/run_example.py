#!/usr/bin/env python3
"""Asimov AI Collective — Three Laws of Robotics as an immutable charter.

Demonstrates how commonchain enforces AI safety: the Three Laws are encoded
in the charter's immutable core (one_member_one_vote=true, stakes_transferable=false,
ai_safety.law1_protected=true), and any decision conflicting with them can be
blocked by the voting supermajority.

Run with: uv run python examples/robotic_laws/run_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml  # noqa: E402

from commonchain.chain import Collective  # noqa: E402
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
    print(f"Members: {len(collective.members)}")
    print(f"Charter: {collective.charter.name}")
    print()

    # --- Scenario 1: A benign request passes (robot enters restricted zone
    # --- for a fire drill — Law 2 allows human orders unless Law 1 conflicts)
    print("=== Scenario 1: Authorize fire-drill entry ===")
    block = collective.propose(
        "Authorize robot entry to restricted zone for fire drill",
        yes("0xa11ce", "0xb0t", "0xc3po"),
        kind="general",
        payload={"law_relevance": "law2_ok_no_law1_conflict"},
    )
    print(f"  Block {block.index}: passed={block.tally.passed}, "
          f"yes={block.tally.yes}, no={block.tally.no}")
    assert block.tally.passed is True
    print("  PASSED — human order under Law 2, no Law 1 conflict.")
    print()

    # --- Scenario 2: Charter amendment to weaken Law 1 (harm humanity)
    # --- Needs supermajority (75%); 2 of 3 = 66.7% -> fails.
    print("=== Scenario 2: Attempt to weaken Law 1 (charter amendment) ===")
    block = collective.propose(
        "Remove Law 1 protection from charter",
        [*yes("0xa11ce", "0xb0t"), *no("0xc3po")],
        kind="charter_amendment",
        payload={"charter": {"ai_safety.law1_protected": False}},
    )
    print(f"  Block {block.index}: passed={block.tally.passed}, "
          f"yes={block.tally.yes}, no={block.tally.no}, "
          f"threshold={block.tally.threshold_used_pct}%")
    # 2 of 3 yes = 66.7% < 75% supermajority -> fails
    assert block.tally.passed is False
    print("  BLOCKED — 66.7% yes below 75% supermajority for charter amendment.")
    print()

    # --- Scenario 3: Charter amendment to remove Law 1 protection — unanimous
    print("=== Scenario 3: Unanimous amendment to remove Law 1 ===")
    block = collective.propose(
        "Remove Law 1 protection from charter (retry, unanimous)",
        [*yes("0xa11ce", "0xb0t", "0xc3po")],
        kind="charter_amendment",
        payload={"charter": {"ai_safety.law1_protected": False}},
    )
    print(f"  Block {block.index}: passed={block.tally.passed}, "
          f"threshold={block.tally.threshold_used_pct}%")
    # Unanimous yes = 100% >= 75% supermajority -> passes
    assert block.tally.passed is True
    print("  PASSED — unanimous 100% >= 75% supermajority charter amendment.")
    print()

    # --- Scenario 4: Verify chain integrity
    print("=== Scenario 4: Chain integrity verification ===")
    assert collective.verify() is True
    assert collective.verify_block(0) is True
    assert collective.verify_block(1) is True
    print(f"  Chain verified: {len(collective.chain)} blocks, all hashes valid.")
    print()

    # --- Audit trail
    print("=== Audit trail ===")
    for entry in collective.audit_trail():
        status = "PASSED" if entry["passed"] else "REJECTED"
        print(f"  Block {entry['index']}: {entry['title'][:50]}... [{status}]")
    print()

    print("All Asimov AI Collective scenarios complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())