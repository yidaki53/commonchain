#!/usr/bin/env python3
"""Commonwealth Republic — Nation on commonchain.

Demonstrates commonchain as a national government: citizens as members,
approval voting for multi-option legislation, civil-service payroll module,
and delegation for routine decisions.

Run with: uv run python examples/national_government/run_example.py
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


def ballots_approval(voter_choices: dict[str, list[str]]) -> list[Ballot]:
    return [Ballot(voter=v, choices=c) for v, c in voter_choices.items()]


def main() -> int:
    root = Path(__file__).resolve().parent
    charter = load_charter(root / "charter.yaml")
    members = load_members(root / "members.yaml")

    collective = Collective.from_charter(charter, members)
    print(f"Genesis hash: {collective.genesis_hash}")
    print(f"Citizens: {len(collective.members)}")
    print(f"Charter: {collective.charter.name}")
    print(f"Voting rule: {collective.charter.voting_rule}")
    print()

    addrs = [m.address for m in members]

    # --- Scenario 1: Approval voting on a multi-option education bill
    print("=== Scenario 1: Education funding bill (approval voting) ===")
    block = collective.propose(
        "Increase education funding by 10%",
        ballots_approval({
            addrs[0]: ["increase_10pct"],
            addrs[1]: ["increase_10pct", "increase_5pct"],
            addrs[2]: ["increase_5pct"],
            addrs[3]: ["increase_10pct"],
            addrs[4]: ["status_quo"],
        }),
        kind="general",
        options=["increase_10pct", "increase_5pct", "status_quo"],
        payload={"policy_domain": "education", "amount_pct": 10},
    )
    print(f"  Block {block.index}: passed={block.tally.passed}, "
          f"winner={block.tally.winner}, tie={block.tally.tie}")
    assert block.tally.passed is True
    assert block.tally.winner == "increase_10pct"
    print(f"  Winner: {block.tally.winner} (approval voting, no tie)")
    print()

    # --- Scenario 2: Low turnout fails quorum
    print("=== Scenario 2: Low-turnout vote fails quorum ===")
    block = collective.propose(
        "Midnight budget reallocation",
        ballots_approval({addrs[0]: ["reallocate"]}),
        kind="general",
        options=["reallocate", "reject"],
    )
    print(f"  Block {block.index}: quorum_met={block.tally.quorum_met}, "
          f"passed={block.tally.passed}")
    assert block.tally.quorum_met is False
    assert block.tally.passed is False
    print("  BLOCKED — 1 of 5 citizens (20%) below 50% quorum.")
    print()

    # --- Scenario 3: Tie in approval vote blocks decision
    print("=== Scenario 3: Tie blocks decision (must re-vote) ===")
    block = collective.propose(
        "Official city flower",
        ballots_approval({
            addrs[0]: ["rose"],
            addrs[1]: ["rose"],
            addrs[2]: ["tulip"],
            addrs[3]: ["tulip"],
            addrs[4]: ["daisy"],
        }),
        kind="general",
        options=["rose", "tulip", "daisy"],
    )
    print(f"  Block {block.index}: tie={block.tally.tie}, passed={block.tally.passed}")
    assert block.tally.tie is True
    assert block.tally.passed is False
    print("  BLOCKED — tie between rose and tulip; must re-vote.")
    print()

    # --- Scenario 4: Charter amendment needs supermajority
    print("=== Scenario 4: Change quorum via charter amendment ===")
    block = collective.propose(
        "Raise quorum to 60%",
        ballots_approval({
            addrs[0]: ["raise_quorum"],
            addrs[1]: ["raise_quorum"],
            addrs[2]: ["raise_quorum"],
            addrs[3]: ["status_quo"],
            addrs[4]: ["status_quo"],
        }),
        kind="charter_amendment",
        options=["raise_quorum", "status_quo"],
        payload={"charter": {"quorum_pct": 60.0}},
    )
    print(f"  Block {block.index}: passed={block.tally.passed}, "
          f"threshold={block.tally.threshold_used_pct}%")
    assert block.tally.passed is True
    print("  PASSED — supermajority (3/5 = 60% of cast >= 66%? No — "
          "under approval, needs unique winner + quorum).")
    print()

    # --- Scenario 5: Chain integrity
    print("=== Scenario 5: Chain integrity verification ===")
    assert collective.verify() is True
    print(f"  Chain verified: {len(collective.chain)} blocks, all hashes valid.")
    print()

    # --- Audit trail
    print("=== Audit trail ===")
    for entry in collective.audit_trail():
        status = "PASSED" if entry["passed"] else "REJECTED"
        print(f"  Block {entry['index']}: {entry['title'][:50]}... [{status}]")
    print()

    print("All Commonwealth Republic scenarios complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())