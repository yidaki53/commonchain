"""Manager-replacement tests: hiring, firing, mandates, rotation.

Every classic manager function is a vote-gated decision block here. These
tests prove the chain performs management without a managerial class:
onboarding/offboarding by vote, role assignment by vote, and -- crucially --
that coordination power always expires instead of calcifying into a boss.
"""

from __future__ import annotations

import pytest
from conftest import yes

from commonchain.chain import Collective, GovernanceError


def _mandate_payload(assignee="0xaaa", role="facilitator", term=3):
    return {
        "assignee": assignee,
        "role": role,
        "scope": "test scope",
        "term_blocks": term,
    }


def test_hiring_is_a_vote_not_a_boss_decision(collective: Collective) -> None:
    block = collective.propose(
        "Hire Dana",
        yes("0xaaa", "0xbbb"),
        kind="membership",
        payload={"action": "add", "member": {"address": "0xddd"}},
    )
    assert block.tally.passed is True
    assert "0xddd" in collective.members


def test_firing_is_a_vote_not_a_boss_decision(collective: Collective) -> None:
    block = collective.propose(
        "Remove Cara",
        yes("0xaaa", "0xbbb"),
        kind="membership",
        payload={"action": "remove", "address": "0xccc"},
    )
    assert block.tally.passed is True
    assert collective.members["0xccc"].active is False


def test_failed_hire_changes_nothing(collective: Collective) -> None:
    block = collective.propose(
        "Hire Mallory",
        yes("0xaaa"),
        kind="membership",
        payload={"action": "add", "member": {"address": "0xeee"}},
    )
    assert block.tally.passed is False
    assert "0xeee" not in collective.members


def test_mandate_grants_a_named_time_limited_role(
    collective: Collective,
) -> None:
    block = collective.propose(
        "Alice facilitates",
        yes("0xaaa", "0xbbb"),
        kind="mandate",
        payload=_mandate_payload(),
    )
    assert block.tally.passed is True
    assert len(collective.mandates) == 1
    m = collective.mandates[0]
    assert m["role"] == "facilitator"
    assert m["assignee"] == "0xaaa"
    assert m["expires_at_block"] == block.index + 3


def test_mandate_grants_no_extra_votes(collective: Collective) -> None:
    """The facilitator's ballot still counts exactly once."""
    collective.propose(
        "Alice facilitates",
        yes("0xaaa", "0xbbb"),
        kind="mandate",
        payload=_mandate_payload(),
    )
    block = collective.propose("Budget", yes("0xaaa"), kind="general")
    assert block.tally.yes == 1


def test_mandate_expires_and_must_be_renewed_by_vote(
    collective: Collective,
) -> None:
    collective.propose(
        "Alice facilitates",
        yes("0xaaa", "0xbbb"),
        kind="mandate",
        payload=_mandate_payload(term=2),
    )
    assert len(collective.active_mandates()) == 1
    # One more decision block passes; the mandate lapses.
    collective.propose("Any business", yes("0xaaa", "0xbbb", "0xccc"))
    assert collective.active_mandates() == []


def test_mandate_for_outsider_is_rejected(collective: Collective) -> None:
    with pytest.raises(GovernanceError, match="not an active member"):
        collective.propose(
            "Outsider runs things",
            yes("0xaaa", "0xbbb"),
            kind="mandate",
            payload=_mandate_payload(assignee="0xevil"),
        )


def test_mandate_needs_a_positive_term(collective: Collective) -> None:
    with pytest.raises(GovernanceError, match="term_blocks must be positive"):
        collective.propose(
            "Permanent boss",
            yes("0xaaa", "0xbbb", "0xccc"),
            kind="mandate",
            payload=_mandate_payload(term=0),
        )


def test_mandate_needs_a_named_role(collective: Collective) -> None:
    with pytest.raises(GovernanceError, match="named role"):
        collective.propose(
            "Vague power",
            yes("0xaaa", "0xbbb"),
            kind="mandate",
            payload=_mandate_payload(role=""),
        )


def test_failed_mandate_grants_nothing(collective: Collective) -> None:
    block = collective.propose(
        "Bob coordinates",
        yes("0xaaa"),
        kind="mandate",
        payload=_mandate_payload(assignee="0xbbb", role="coordinator"),
    )
    assert block.tally.passed is False
    assert collective.mandates == []


def test_history_survives_amendments(collective: Collective) -> None:
    """Constitutional versioning: amendments never invalidate earlier blocks."""
    b0 = collective.propose("Ordinary business", yes("0xaaa", "0xbbb"))
    assert b0.charter_version == 0
    collective.propose(
        "Lower quorum",
        yes("0xaaa", "0xbbb", "0xccc"),
        kind="charter_amendment",
        payload={"charter": {"quorum_pct": 30.0}},
    )
    assert collective.charter_version == 2
    b2 = collective.propose("Later business", yes("0xaaa", "0xbbb"))
    assert b2.charter_version == 1
    assert b2.charter_hash != b0.charter_hash
    assert collective.verify() is True


def test_tampered_charter_history_is_detected(
    collective: Collective,
) -> None:
    collective.propose("Business", yes("0xaaa", "0xbbb"))
    collective.propose(
        "Lower quorum",
        yes("0xaaa", "0xbbb", "0xccc"),
        kind="charter_amendment",
        payload={"charter": {"quorum_pct": 30.0}},
    )
    collective.charter_history[0].mission = "rewritten history"
    assert collective.verify() is False
