"""Tests for the liquid delegation module.

The critical properties are the ones that keep delegation from silently
rebuilding the hierarchy the project exists to remove:

* delegate weight stays 1 (so weighted voting is unrepresentable);
* delegation cycles terminate and never lose a vote silently;
* chain depth is capped;
* concentration is *measured*, not assumed away.
"""

from __future__ import annotations

import random

import pytest

from commonchain.governance import Ballot
from commonchain.modules import delegation as d


def test_self_delegation_is_refused() -> None:
    rng = random.Random(0)
    m = d.build_delegation_map(["a", "b", "c"], 1.0, rng)
    assert all(k != v for k, v in m.items()), "self-delegation would be a no-op loop"


def test_cycle_terminates_and_is_counted() -> None:
    """A -> B -> A must not hang, and must be reported."""
    res = d.resolve_delegations(["a", "b"], {"a": "b", "b": "a"})
    assert res.cycles_detected >= 1
    # Nobody is silently dropped: both still participate as voters.
    assert res.n_effective_voters >= 1


def test_three_cycle_terminates() -> None:
    # max_depth must exceed the cycle length for the cycle itself to be
    # *detected*; with the default depth of 1 the chain is truncated first.
    # Both outcomes are safe (see resolve_delegations), but they are different
    # code paths, so the cycle detector is tested explicitly here.
    res = d.resolve_delegations(
        ["a", "b", "c"], {"a": "b", "b": "c", "c": "a"}, max_depth=10
    )
    assert res.cycles_detected >= 1


def test_cycle_below_depth_cap_is_truncated_not_detected() -> None:
    """Depth cap is the primary guard; cycle detection is the backstop.

    With max_depth=1 a->b->c never reaches the cycle, so the chain is truncated
    instead. That is the safe outcome, but it must be *counted*, never silent.
    """
    res = d.resolve_delegations(["a", "b", "c"], {"a": "b", "b": "c", "c": "a"})
    assert res.chains_truncated >= 1
    assert res.resolved.get("a") is None or res.resolved["a"] != "a"


def test_simple_chain_resolves_to_terminal_voter() -> None:
    res = d.resolve_delegations(["a", "b", "c"], {"a": "b"})
    assert res.resolved["a"] == "b"
    assert res.cycles_detected == 0


def test_transitive_chain_follows_to_the_end() -> None:
    res = d.resolve_delegations(["a", "b", "c"], {"a": "b", "b": "c"}, max_depth=5)
    assert res.resolved["a"] == "c", "a delegates to b, b delegates to c"
    assert res.chains_truncated == 0


def test_depth_cap_truncates_long_chains() -> None:
    res = d.resolve_delegations(
        ["a", "b", "c", "d", "e"], {"a": "b", "b": "c", "c": "d", "d": "e"},
        max_depth=2,
    )
    assert res.chains_truncated >= 1


def test_delegation_to_unknown_address_is_ignored() -> None:
    res = d.resolve_delegations(["a"], {"a": "ghost"})
    assert res.resolved == {}


def test_delegate_weight_is_still_one() -> None:
    """The invariant that stops delegation becoming shareholder plutocracy."""
    with pytest.raises(ValueError, match="weight must be 1"):
        Ballot(voter="delegate", yes=True, weight=50)


def test_concentration_detects_a_super_delegate() -> None:
    """If most members funnel through one caster, concentration must spike."""
    addrs = [f"a{i}" for i in range(10)]
    resolved = {a: "a0" for a in addrs[1:]}  # 9 members delegate to a0
    max_share, hhi = d.concentration(addrs, resolved)
    # All 9 cast ballots are a0's, so a0 casts 100% of the delegated ballots.
    assert max_share == pytest.approx(1.0)
    assert hhi > 0.8, "near-total concentration should show up in the HHI"


def test_concentration_is_zero_without_delegation() -> None:
    max_share, hhi = d.concentration(["a", "b", "c"], {})
    assert max_share == 0.0 and hhi == 0.0


def test_spread_delegation_has_low_concentration() -> None:
    addrs = [f"a{i}" for i in range(10)]
    resolved = {addrs[i]: addrs[(i + 1) % 10] for i in range(5)}
    max_share, hhi = d.concentration(addrs, resolved)
    # 5 distinct casters, 1 ballot each -> perfectly even: HHI = 5 * (1/5)^2.
    assert hhi == pytest.approx(0.2)
    assert max_share == pytest.approx(0.2)
