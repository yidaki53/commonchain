"""Contract invariants.

These are the properties the whole project exists to guarantee. They are
asserted in Python here and mirrored in Solidity under ``contracts/test``:

1. equity is non-transferable (stakes are soulbound);
2. every member's vote weight is equal;
3. the immutable democratic core cannot be voted away.

Money-specific guarantees (funds never leaving the member set) live with the
payroll module in ``test_payroll.py``, because not every organisation has
money: the core must hold for parties and volunteer networks too.
"""

from __future__ import annotations

import pytest
from conftest import no, yes

from commonchain.chain import Collective, GovernanceError


# --- 1. equity is non-transferable ---------------------------------------
def test_transferable_stakes_are_rejected_at_charter_time() -> None:
    from commonchain.models import Charter

    with pytest.raises(ValueError, match="transferable"):
        Charter.model_validate(
            {
                "name": "Bad Co",
                "mission": "m",
                "stakes_transferable": True,
            }
        )


def test_no_api_exists_to_transfer_a_stake(collective: Collective) -> None:
    forbidden = ("transfer", "transfer_stake", "sell_stake", "assign_equity")
    for name in forbidden:
        assert not hasattr(collective, name), f"{name} must not exist"


def test_immutable_core_cannot_be_voted_away(collective: Collective) -> None:
    """A hostile majority cannot vote itself into shareholder-style control."""
    with pytest.raises(GovernanceError, match="immutable democratic core"):
        collective.propose(
            "Make stakes transferable",
            yes("0xaaa", "0xbbb"),
            kind="charter_amendment",
            payload={"charter": {"stakes_transferable": True}},
        )


def test_immutable_core_cannot_be_voted_away_even_unanimously(
    collective: Collective,
) -> None:
    with pytest.raises(GovernanceError, match="immutable democratic core"):
        collective.propose(
            "Drop one-worker-one-vote",
            yes("0xaaa", "0xbbb", "0xccc"),
            kind="charter_amendment",
            payload={"charter": {"one_member_one_vote": False}},
        )


def test_amendable_modules_can_change(collective: Collective) -> None:
    block = collective.propose(
        "Switch payroll to labour-hours",
        yes("0xaaa", "0xbbb", "0xccc"),
        kind="charter_amendment",
        payload={"charter": {"modules.payroll.policy": "labor_hours"}},
    )
    assert block.tally.passed is True
    assert collective.charter.modules["payroll"]["policy"] == "labor_hours"


def test_amending_one_module_preserves_siblings(collective: Collective) -> None:
    collective.charter.modules["dispute"] = {"mode": "kleros"}
    collective.propose(
        "Switch payroll policy",
        yes("0xaaa", "0xbbb", "0xccc"),
        kind="charter_amendment",
        payload={"charter": {"modules.payroll.policy": "seniority"}},
    )
    assert collective.charter.modules["dispute"] == {"mode": "kleros"}
    assert collective.charter.modules["payroll"]["policy"] == "seniority"


def test_offboarding_burns_the_stake_rather_than_moving_it(
    collective: Collective,
) -> None:
    """No code path moves a departed member's stake to someone else."""
    alice_before = collective.members["0xaaa"].metrics["labor_hours"]
    collective.deactivate_member("0xccc")
    assert collective.members["0xccc"].active is False
    # The record still exists (audit trail) but yields no rights, and nobody
    # inherits anything from it.
    assert collective.members["0xaaa"].metrics["labor_hours"] == alice_before
    assert not hasattr(collective, "transfer_stake")
    assert not hasattr(collective, "distribute")


# --- 2. equal vote weights -----------------------------------------------
def test_all_ballots_have_unit_weight(collective: Collective) -> None:
    block = collective.propose("Anything", yes("0xaaa", "0xbbb"))
    assert all(b.weight == 1 for b in block.tally.ballots)


def test_a_high_earning_member_has_no_more_votes(collective: Collective) -> None:
    """Bob has 4x Alice's recorded hours; his vote still counts once."""
    block = collective.propose("Equal say", [*yes("0xbbb"), *no("0xaaa")])
    assert block.tally.yes == 1
    assert block.tally.no == 1


def test_genesis_hash_changes_when_charter_changes(collective: Collective) -> None:
    """History is anchored to a specific charter: rewriting it reparents all."""
    original = collective.genesis_hash
    collective.charter.mission = "A different mission entirely."
    assert collective.genesis_hash != original
