# The payroll module: revenue sharing for companies and co-ops.
#
# Payroll is ONE pilot example of organisation-specific functionality plugged
# into the universal decision-record core. The core (members, votes, chain)
# knows nothing about money; this module reads core state (active members and
# their contribution metrics) and computes payouts. A political party or a
# volunteer network would simply not enable it -- and the core works the same.
#
# Enabling it in a charter:
#   modules:
#     payroll:
#       policy: equal            # equal | labor_hours | seniority
#       stable_base_share: 0.5   # fraction paid as equal stable base
#
# Policies:
#   equal        split the whole pool equally.
#   labor_hours  pay the stable base equally, split the rest by labor_hours.
#   seniority    pay the stable base equally, split the rest by tenure.
#
# The stable base addresses the precarity documented by Merk et al. (2026):
# every worker gets a predictable floor regardless of the variable policy.


from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a runtime cycle
    from ..chain import Collective
    from ..models import Member

POLICIES = ("equal", "labor_hours", "seniority")


class PayrollError(Exception):
    """Raised when payroll cannot be computed for a collective."""


def is_enabled(collective: "Collective") -> bool:
    """A collective has payroll iff its charter enables the payroll module."""
    return "payroll" in (collective.charter.modules or {})


def config(collective: "Collective") -> dict:
    """Return this collective's payroll config (defaults if keys are absent)."""
    raw = (collective.charter.modules or {}).get("payroll") or {}
    return {
        "policy": raw.get("policy", "equal"),
        "stable_base_share": float(raw.get("stable_base_share", 0.5)),
    }


def require_enabled(collective: "Collective") -> dict:
    """Return the payroll config, or raise if this org has no payroll.

    This is the guard every payroll entry point uses: a party or volunteer
    network without the module gets a clear error, not a silent zero split.
    """
    if not is_enabled(collective):
        raise PayrollError(
            "this collective has no payroll module enabled "
            "(add `modules: {payroll: ...}` to the charter)"
        )
    cfg = config(collective)
    if cfg["policy"] not in POLICIES:
        raise PayrollError(f"unknown payroll policy: {cfg['policy']!r}")
    if not 0 <= cfg["stable_base_share"] <= 1:
        raise PayrollError("stable_base_share must be between 0 and 1")
    return cfg


def distribute(
    collective: "Collective", pool: float
) -> dict[str, float]:
    """Split ``pool`` among active members per this collective's payroll config.

    Invariant: only active members ever receive funds -- money never leaves the
    member set. Returns a mapping address -> payout.
    """
    cfg = require_enabled(collective)
    if pool < 0:
        raise PayrollError("cannot distribute a negative amount")
    members = collective.active_members()
    if not members:
        raise PayrollError("no active members to pay")

    shares = _compute_shares(members, pool, cfg["policy"], cfg["stable_base_share"])
    total = sum(shares.values())
    if total > 0:  # normalise away float drift so the sum equals the pool
        for k in shares:
            shares[k] = shares[k] * pool / total
    return shares


def _compute_shares(
    members: list["Member"], pool: float, policy: str, stable_base_share: float
) -> dict[str, float]:
    base = pool * stable_base_share
    variable = pool - base

    base_each = base / len(members)
    shares = {m.address: base_each for m in members}
    if variable <= 0:
        return shares

    if policy == "equal":
        extra = variable / len(members)
        for m in members:
            shares[m.address] += extra
    elif policy == "labor_hours":
        # Reads the member's "labor_hours" metric (see models.Member.metrics).
        # A club would use a different policy -- or none at all.
        def _hours(m: "Member") -> float:
            return float(m.metrics.get("labor_hours", 0.0))

        total_hours = sum(_hours(m) for m in members)
        if total_hours <= 0:
            extra = variable / len(members)
            for m in members:
                shares[m.address] += extra
        else:
            for m in members:
                shares[m.address] += variable * (_hours(m) / total_hours)
    elif policy == "seniority":
        now = time.time()
        ages = {m.address: max(0.0, now - m.joined_at) for m in members}
        total_age = sum(ages.values())
        if total_age <= 0:
            extra = variable / len(members)
            for m in members:
                shares[m.address] += extra
        else:
            for m in members:
                shares[m.address] += variable * (ages[m.address] / total_age)
    else:  # pragma: no cover - validated in require_enabled
        raise PayrollError(f"unknown payroll policy: {policy!r}")
    return shares
