# The payroll pilot. Payroll is an OPTIONAL module: the fixture collective
# (see conftest.py) enables it, and the last tests cover the opt-out case --
# a party or volunteer network without the module.

from __future__ import annotations

import time

import pytest

from commonchain.chain import Collective
from commonchain.models import Member
from commonchain.modules import payroll
from commonchain.modules.payroll import PayrollError


def _policy(collective: Collective, policy: str) -> None:
    collective.charter.modules["payroll"]["policy"] = policy


def test_equal_split_is_equal(collective: Collective) -> None:
    shares = payroll.distribute(collective, 900.0)
    assert shares["0xaaa"] == pytest.approx(300.0)
    assert shares["0xbbb"] == pytest.approx(300.0)
    assert shares["0xccc"] == pytest.approx(300.0)


def test_payouts_go_only_to_active_members(collective: Collective) -> None:
    shares = payroll.distribute(collective, 1000.0)
    assert set(shares) == {m.address for m in collective.active_members()}
    assert all(v > 0 for v in shares.values())


def test_payouts_conserve_value(collective: Collective) -> None:
    shares = payroll.distribute(collective, 1000.0)
    assert sum(shares.values()) == pytest.approx(1000.0)


def test_offboarded_member_stops_receiving_payouts(
    collective: Collective,
) -> None:
    collective.deactivate_member("0xccc")
    shares = payroll.distribute(collective, 900.0)
    assert "0xccc" not in shares
    assert set(shares) == {"0xaaa", "0xbbb"}


def test_stable_base_is_paid_regardless_of_policy(collective: Collective) -> None:
    """Every worker gets at least the stable base share (anti-precarity)."""
    _policy(collective, "labor_hours")
    shares = payroll.distribute(collective, 1000.0)
    floor = 1000.0 * payroll.config(collective)["stable_base_share"] / 3
    for addr, amt in shares.items():
        assert amt >= floor - 1e-9, f"{addr} fell below the stable floor"


def test_labor_hours_tracks_hours(collective: Collective) -> None:
    _policy(collective, "labor_hours")
    shares = payroll.distribute(collective, 1000.0)
    # Bob did 20/35 of the variable half; Cara 5/35.
    variable = 500.0
    assert shares["0xbbb"] == pytest.approx(500.0 / 3 + variable * 20 / 35)
    assert shares["0xccc"] == pytest.approx(500.0 / 3 + variable * 5 / 35)
    assert shares["0xbbb"] > shares["0xccc"]


def test_labor_hours_falls_back_to_equal_when_no_hours(
    collective: Collective,
) -> None:
    for m in collective.members.values():
        m.metrics["labor_hours"] = 0.0
    _policy(collective, "labor_hours")
    shares = payroll.distribute(collective, 900.0)
    assert shares["0xaaa"] == pytest.approx(300.0)


def test_seniority_favours_earlier_joiners(collective: Collective) -> None:
    _policy(collective, "seniority")
    # Backdate two members so seniority is deterministic.
    collective.members["0xaaa"].joined_at = time.time() - 1000
    collective.members["0xbbb"].joined_at = time.time() - 500
    collective.members["0xccc"].joined_at = time.time() - 100
    shares = payroll.distribute(collective, 1000.0)
    assert shares["0xaaa"] > shares["0xbbb"] > shares["0xccc"]


def test_zero_base_share_uses_full_pool_variable(
    collective: Collective,
) -> None:
    collective.charter.modules["payroll"]["stable_base_share"] = 0.0
    shares = payroll.distribute(collective, 600.0)
    assert shares["0xaaa"] == pytest.approx(200.0)


def test_negative_pool_raises(collective: Collective) -> None:
    with pytest.raises(PayrollError, match="negative amount"):
        payroll.distribute(collective, -1.0)


def test_no_members_raises(charter) -> None:
    col = Collective(charter=charter)
    with pytest.raises(PayrollError, match="no active members"):
        payroll.distribute(col, 100.0)


def test_payroll_is_opt_in(charter) -> None:
    """A collective without the module (party, volunteer network) has none."""
    charter.modules.pop("payroll", None)
    col = Collective.from_charter(charter, [Member(address="0xaaa")])
    assert payroll.is_enabled(col) is False
    with pytest.raises(PayrollError, match="no payroll module"):
        payroll.distribute(col, 100.0)


def test_unknown_policy_raises(collective: Collective) -> None:
    _policy(collective, "plutocracy")
    with pytest.raises(PayrollError, match="unknown payroll policy"):
        payroll.distribute(collective, 100.0)
