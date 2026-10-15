"""Liquid delegation module -- optional, and deliberately dangerous.

Why this exists
---------------
Night 1's headline finding is that *turnout*, not thresholds, is the binding
constraint, and the natural remedy is liquid (delegated) voting. But delegation
is not a neutral turnout fix. Alouf-Heffetz, Inamdar, Jain, More & Talmon
("Controlling Delegations in Liquid Democracy", arXiv:2403.07558) state the
problem directly:

    "This results in a power structure in which certain agents possess more
     voting weight than others. As a result, it opens up certain possibilities
     of vote manipulation, including control and bribery, that do not exist in
     standard voting scenarios of direct democracy."

So this module is built to *measure* the trade rather than assume it away.

The load-bearing design decision
--------------------------------
**Delegate weight stays exactly 1.** Delegation changes *who casts* a ballot,
never its weight. Naive weighted delegation would recreate precisely the
shareholder plutocracy this project exists to abolish -- a member who
accumulates 50 delegations would hold 50 votes. Because ``Ballot.weight`` is
pinned to 1 by ``governance.py``'s validator, weighted delegation is
*unrepresentable* here, and the existing invariant tests keep passing unchanged.
That is the signal that the democratic floor survived the addition.

Cycles
------
A -> B -> C -> A would otherwise make vote-counting undefined or loop forever.
Resolution is deterministic and tested: every member in a detected cycle falls
back to casting their own ballot (or abstaining). See ``resolve_delegations``.

Note on sourcing: the widely-cited "transitivity problem" treatment could not
be verified from a primary source during this work, so no citation is claimed
for it. Cycle handling below is validated by test, not by appeal to literature.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DelegationConfig:
    """Delegation policy. All-zero by default: delegation is opt-in."""

    enabled: bool = False
    delegation_rate: float = 0.0   # fraction of members who delegate
    max_depth: int = 1             # how far a transitive chain may run
    expire_after: int = 0          # 0 = never expire; else N blocks


@dataclass
class DelegationResult:
    """What delegation did, including its costs."""

    n_delegators: int = 0
    n_effective_voters: int = 0
    cycles_detected: int = 0
    chains_truncated: int = 0
    max_delegate_share: float = 0.0
    delegate_hhi: float = 0.0
    # member -> the address whose ballot they are represented by
    resolved: dict[str, str] = field(default_factory=dict)


def build_delegation_map(
    addrs: list[str], delegation_rate: float, rng, max_depth: int = 1
) -> dict[str, str]:
    """Assign each willing member a delegate, skipping self-delegation."""
    delegators = [a for a in addrs if rng.random() < delegation_rate]
    return {
        a: d for a in delegators
        if (d := rng.choice(addrs)) != a
    }


def resolve_delegations(
    addrs: list[str],
    delegations: dict[str, str],
    max_depth: int = 1,
) -> DelegationResult:
    """Follow each delegation chain to the member who actually votes.

    Terminates on cycles by falling back to direct voting, and truncates chains
    longer than ``max_depth``. Both events are counted rather than silently
    swallowed -- a chain that silently vanishes is an uncounted vote.
    """
    res = DelegationResult(n_delegators=len(delegations))
    known = set(addrs)

    for start in delegations:
        seen = [start]
        cur = delegations.get(start)
        depth = 0
        while cur is not None and cur in known:
            if cur in seen:
                res.cycles_detected += 1
                break  # cycle: this member votes for themselves
            seen.append(cur)
            depth += 1
            if depth > max_depth:
                res.chains_truncated += 1
                break
            nxt = delegations.get(cur)
            if nxt is None:
                res.resolved[start] = cur  # terminal: cur casts the ballot
                break
            cur = nxt

    effective = {a for a in addrs if a not in res.resolved} | set(res.resolved.values())
    res.n_effective_voters = len(effective)
    return res


def concentration(addrs: list[str], resolved: dict[str, str]) -> tuple[float, float]:
    """(max_share, hhi) of votes actually cast, by casting member.

    This is the metric that decides whether delegation is safe: if a small
    number of members end up casting most ballots, delegation has quietly
    rebuilt a representative class -- the thing the project rejects.
    """
    if not resolved:
        return 0.0, 0.0
    counts: dict[str, int] = {a: 0 for a in addrs}
    for caster in resolved.values():
        counts[caster] += 1
    total = sum(counts.values())
    if total == 0:
        return 0.0, 0.0
    shares = [c / total for c in counts.values()]
    return max(shares), sum(s * s for s in shares)
