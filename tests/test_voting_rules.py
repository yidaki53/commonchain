"""Voting-rule tests: binary regression, plurality, approval, rule switching.

The binary rule must behave exactly as before (the whole existing suite is the
regression); plurality and approval add multi-option decisions for clubs:
elect a captain, pick a route or a book. Ties are recorded, never broken. All
rules keep the democratic floor: weight is pinned to 1.
"""

from __future__ import annotations

import pytest

from commonchain.chain import Collective
from commonchain.governance import Ballot, Proposal, evaluate
from commonchain.models import Charter, Member


def _club_charter(rule: str) -> Charter:
    return Charter.model_validate(
        {
            "name": "Test Club",
            "mission": "A club that votes on things.",
            "kind": "club",
            "quorum_pct": 50.0,
            "pass_pct": 50.0,
            "supermajority_pct": 66.0,
            "voting_rule": rule,
        }
    )


def _members(n: int = 5) -> list[Member]:
    return [Member(address=f"0x{i:x}") for i in range(n)]


def _ballots(votes: dict[str, str]) -> list[Ballot]:
    return [Ballot(voter=a, choices=[c]) for a, c in votes.items()]


# --- charter surface -------------------------------------------------------

def test_voting_rule_defaults_to_binary() -> None:
    c = Charter.model_validate({"name": "x", "mission": "m"})
    assert c.voting_rule == "binary"


def test_unknown_voting_rule_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown voting rule"):
        Charter.model_validate(
            {"name": "x", "mission": "m", "voting_rule": "soviet"}
        )


def test_voting_rule_is_amendable_policy(collective: Collective) -> None:
    """Switching rules is a policy decision, not a constitutional one."""
    block = collective.propose(
        "Adopt approval voting",
        [Ballot(voter=a, yes=True) for a in ("0xaaa", "0xbbb", "0xccc")],
        kind="charter_amendment",
        payload={"charter": {"voting_rule": "approval"}},
    )
    assert block.tally.passed is True
    assert collective.charter.voting_rule == "approval"


# --- plurality -------------------------------------------------------------

def test_plurality_elects_a_unique_winner() -> None:
    col = Collective.from_charter(_club_charter("plurality"), _members(5))
    block = col.propose(
        "Club captain",
        _ballots(
            {
                "0x0": "alice",
                "0x1": "alice",
                "0x2": "bob",
                "0x3": "cara",
                "0x4": "alice",
            }
        ),
        options=["alice", "bob", "cara"],
    )
    t = block.tally
    assert t.passed is True
    assert t.winner == "alice"
    assert t.option_counts == {"alice": 3, "bob": 1, "cara": 1}
    assert t.winner_share_pct == pytest.approx(60.0)
    assert t.voting_rule == "plurality"


def test_plurality_tie_is_recorded_and_blocks_the_decision() -> None:
    col = Collective.from_charter(_club_charter("plurality"), _members(4))
    block = col.propose(
        "Saturday route",
        _ballots(
            {"0x0": "river", "0x1": "parks", "0x2": "river", "0x3": "parks"}
        ),
        options=["river", "parks", "hills"],
    )
    t = block.tally
    assert t.tie is True
    assert t.winner is None
    assert t.passed is False
    assert len(col.chain) == 1  # the tie is on the record; revote next


def test_plurality_requires_exactly_one_choice() -> None:
    col = Collective.from_charter(_club_charter("plurality"), _members(3))
    with pytest.raises(ValueError, match="exactly one choice"):
        col.propose(
            "Double dip",
            [Ballot(voter="0x0", choices=["river", "parks"])],
            options=["river", "parks"],
        )


def test_plurality_rejects_choice_outside_options() -> None:
    col = Collective.from_charter(_club_charter("plurality"), _members(3))
    with pytest.raises(ValueError, match="not among proposal options"):
        col.propose(
            "Write-in", _ballots({"0x0": "mallory"}), options=["river", "parks"]
        )


def test_plurality_requires_options() -> None:
    col = Collective.from_charter(_club_charter("plurality"), _members(3))
    with pytest.raises(ValueError, match="options"):
        col.propose("No options", _ballots({"0x0": "river"}))


def test_plurality_quorum_still_applies() -> None:
    col = Collective.from_charter(_club_charter("plurality"), _members(5))
    block = col.propose(
        "Low turnout",
        _ballots({"0x0": "river"}),  # 1/5 = 20% < 50% quorum
        options=["river", "parks"],
    )
    assert block.tally.quorum_met is False
    assert block.tally.passed is False


# --- approval --------------------------------------------------------------

def test_approval_counts_approvals_per_option() -> None:
    col = Collective.from_charter(_club_charter("approval"), _members(4))
    block = col.propose(
        "Which events?",
        [
            Ballot(voter="0x0", choices=["race", "quiz"]),
            Ballot(voter="0x1", choices=["race"]),
            Ballot(voter="0x2", choices=["race", "trip"]),
            Ballot(voter="0x3", choices=["quiz"]),
        ],
        options=["race", "quiz", "trip"],
    )
    t = block.tally
    assert t.option_counts == {"race": 3, "quiz": 2, "trip": 1}
    assert t.winner == "race"
    assert t.passed is True


def test_approval_tie_yields_no_winner() -> None:
    col = Collective.from_charter(_club_charter("approval"), _members(2))
    block = col.propose(
        "Tied approvals",
        [Ballot(voter="0x0", choices=["a"]), Ballot(voter="0x1", choices=["b"])],
        options=["a", "b"],
    )
    assert block.tally.tie is True
    assert block.tally.passed is False


# --- binary regression (default charter) ------------------------------------

def test_binary_rejects_multi_choice_ballots(collective: Collective) -> None:
    with pytest.raises(ValueError, match="only 'yes'/'no'"):
        collective.propose(
            "Confused ballot",
            [Ballot(voter="0xaaa", choices=["yes", "maybe"])],
        )


def test_binary_yes_sugar_normalizes_to_choices(
    collective: Collective,
) -> None:
    block = collective.propose(
        "Sugar",
        [Ballot(voter="0xaaa", yes=True), Ballot(voter="0xbbb", yes=False)],
    )
    assert block.tally.yes == 1
    assert block.tally.no == 1
    assert block.tally.winner is None
    assert block.tally.voting_rule == "binary"


def test_contradictory_yes_and_choices_rejected() -> None:
    with pytest.raises(ValueError, match="contradictory"):
        Ballot(voter="0xaaa", yes=True, choices=["no"])


def test_empty_ballot_rejected() -> None:
    with pytest.raises(ValueError, match="at least one choice"):
        Ballot(voter="0xaaa")


def test_duplicate_choices_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate choices"):
        Ballot(voter="0xaaa", choices=["a", "a"])


def test_weight_must_be_one_under_every_rule() -> None:
    for choices in (["yes"], ["no"], ["a"], ["a", "b"]):
        with pytest.raises(ValueError, match="weight must be 1"):
            Ballot(voter="0xaaa", choices=choices, weight=7)


def test_evaluate_direct_under_plurality() -> None:
    charter = _club_charter("plurality")
    members = _members(3)
    proposal = Proposal(title="Pick", options=["a", "b", "c"])
    tally = evaluate(
        charter,
        members,
        proposal,
        [
            Ballot(voter="0x0", choices=["c"]),
            Ballot(voter="0x1", choices=["c"]),
            Ballot(voter="0x2", choices=["a"]),
        ],
    )
    assert tally.winner == "c"
    assert tally.passed is True

