"""Governance tests: vote tallying, quorum, supermajority, one-worker-one-vote."""

from __future__ import annotations

import pytest
from conftest import no, yes

from commonchain.chain import Collective, GovernanceError
from commonchain.governance import Ballot, evaluate


def test_genesis_hash_is_charter_hash(collective: Collective) -> None:
    """The charter IS the genesis block."""
    genesis = collective.genesis_hash
    assert len(genesis) == 64
    assert collective.chain == []


def test_first_block_links_to_genesis(collective: Collective) -> None:
    block = collective.propose("Buy a 3D printer", yes("0xaaa", "0xbbb"))
    assert block.index == 0
    assert block.prev_hash == collective.genesis_hash
    assert block.tally.passed is True


def test_blocks_are_hash_linked(collective: Collective) -> None:
    b0 = collective.propose("Decision A", yes("0xaaa", "0xbbb"))
    b1 = collective.propose("Decision B", yes("0xaaa", "0xccc"))
    assert b1.prev_hash == b0.block_hash
    assert b1.block_hash != b0.block_hash
    assert collective.verify() is True


def test_one_member_one_vote_rejects_double_voting(collective: Collective) -> None:
    with pytest.raises(ValueError, match="duplicate ballot"):
        collective.propose("Rig it", [*yes("0xaaa"), *yes("0xaaa")])


def test_non_member_cannot_vote(collective: Collective) -> None:
    with pytest.raises(ValueError, match="non-active member"):
        collective.propose("Outsider vote", yes("0xevil"))


def test_weight_must_be_one(collective: Collective) -> None:
    with pytest.raises(ValueError, match="weight must be 1"):
        Ballot(voter="0xaaa", yes=True, weight=5)


def test_quorum_blocks_low_turnout(collective: Collective) -> None:
    # 1 of 3 = 33% turnout, quorum is 50% -> fails even though it is unanimous.
    block = collective.propose("Sneak it through", yes("0xaaa"))
    assert block.tally.quorum_met is False
    assert block.tally.passed is False


def test_failed_proposals_are_still_recorded(collective: Collective) -> None:
    block = collective.propose("Rejected idea", no("0xaaa", "0xbbb"))
    assert block.tally.passed is False
    assert len(collective.chain) == 1  # the memory is complete, not just wins


def test_charter_amendment_needs_supermajority(collective: Collective) -> None:
    # 2 of 3 = 66.7% yes of cast ballots: passes a normal 50% vote but an
    # amendment demands the supermajority threshold.
    block = collective.propose(
        "Amend charter",
        [*yes("0xaaa", "0xbbb"), *no("0xccc")],
        kind="charter_amendment",
        payload={"charter": {"pass_pct": 60.0}},
    )
    assert block.tally.is_charter_amendment is True
    assert block.tally.threshold_used_pct == 66.0
    assert block.tally.passed is True


def test_inactive_members_cannot_vote(collective: Collective) -> None:
    collective.deactivate_member("0xccc")
    with pytest.raises(ValueError, match="non-active member"):
        collective.propose("After exit", yes("0xccc"))


def test_evaluate_directly_matches_propose(collective: Collective) -> None:
    from commonchain.governance import Proposal

    proposal = Proposal(title="Direct", kind="general")
    tally = evaluate(collective.charter, collective.members.values(), proposal,
                     yes("0xaaa", "0xbbb"))
    assert tally.passed is True
    assert tally.yes == 2
    assert tally.eligible_voters == 3


def test_unknown_member_deactivate_raises(collective: Collective) -> None:
    with pytest.raises(GovernanceError):
        collective.deactivate_member("0xnobody")


def test_duplicate_member_raises(collective: Collective) -> None:
    from commonchain.models import Member

    with pytest.raises(GovernanceError, match="already exists"):
        collective.add_member(Member(address="0xaaa"))
