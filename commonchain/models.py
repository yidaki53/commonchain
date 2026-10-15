"""Canonical data model for a self-governing collective.

Thesis: every classic manager function -- onboarding/offboarding, assigning
roles and tasks, setting policy, approving decisions -- becomes a vote-gated,
hash-linked decision block. No managerial class is needed: the chain *is* the
manager, owned by the members.

The model is deliberately domain-neutral: worker co-ops, political parties,
volunteer movements and hobby clubs (running, chess, reading, ...) all run on
the same primitives. Organisation-specific behaviour (payroll, dues, etc.)
lives in optional modules, never in the core.

Design notes
------------
* ``Charter`` is the genesis state; its canonical hash is the genesis block hash.
* Every ``DecisionBlock`` links to its predecessor via ``prev_hash`` and is
  gated by a completed vote (one-member-one-vote, never token-weighted).
* Members hold a *soulbound* membership: non-transferable, one vote each.
  There is no code path that transfers membership between members.
* The voting rule (``binary`` / ``plurality`` / ``approval``) is charter
  policy: clubs pick names or routes, co-ops ratify yes/no business.
* Management functions (membership, mandates/roles, policy) execute *only* on
  pass, inside ``Collective._apply_effects``. Unknown business kinds are
  recorded but executed by humans -- ratified, not bossed.
* Optional domain functionality (payroll, dues, disputes) lives in modules
  under ``commonchain.modules``, configured via ``Charter.modules``.
"""

from __future__ import annotations

import hashlib
import json
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CollectiveKind(str, Enum):
    coop = "coop"
    party = "party"
    movement = "movement"
    club = "club"
    generic = "generic"


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON encoding used for all hashing.

    Keys are sorted and whitespace stripped so the same logical object always
    produces the same bytes on any platform.
    """

    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_model(model: BaseModel) -> str:
    """Hash a pydantic model via its canonical JSON form."""

    return sha256_hex(canonical_json(model.model_dump(mode="json")))


class Member(BaseModel):
    """A member of the collective, with a soulbound membership.

    ``metrics`` holds arbitrary named contribution metrics (``labor_hours``
    for co-ops, ``attendance`` for a club, ``miles_run``, ``books_read``, ...).
    The core ignores them entirely; optional modules (e.g. payroll) may read
    them. Metrics are not tradable and confer no votes.
    """

    address: str = Field(description="Wallet address / identity of the member.")
    display_name: str = ""
    joined_at: float = Field(default_factory=time.time)
    metrics: dict[str, float] = Field(default_factory=dict)
    active: bool = True

    @field_validator("address")
    @classmethod
    def _addr_norm(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("member address must be non-empty")
        return v.lower()


class Charter(BaseModel):
    """Genesis configuration of the collective.

    The charter is intentionally split into an *immutable core* (mission,
    one-worker-one-vote) and *amendable policy* (quorum, thresholds,
    jurisdiction wrapper, optional modules). Only the amendable layer can
    change, and only through a super-majority decision block -- this resolves
    the "immutable charter vs amendable modules" open question in favour of a
    fixed democratic floor with a flexible policy layer on top.
    """

    name: str
    mission: str
    kind: CollectiveKind = CollectiveKind.coop
    # --- immutable core (conceptually; enforced by governance rules) ---
    one_member_one_vote: bool = True
    stakes_transferable: bool = False
    # --- amendable policy ---
    quorum_pct: float = Field(default=50.0, ge=0, le=100)
    pass_pct: float = Field(default=50.0, ge=0, le=100)
    supermajority_pct: float = Field(default=66.0, ge=0, le=100)
    # Voting rule for ordinary decisions. ``binary`` is yes/no ratification;
    # ``plurality`` and ``approval`` let clubs elect captains or pick routes,
    # books and venues from a proposal's ``options`` list. Amendable policy,
    # so a collective can switch rules by supermajority.
    voting_rule: str = "binary"
    jurisdiction_module: str = "generic"
    # Optional domain modules and their configs, e.g.
    # {"payroll": {"policy": "equal", "stable_base_share": 0.5}}.
    # Absent modules simply do not apply to this collective.
    modules: dict[str, dict[str, Any]] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    @field_validator("stakes_transferable")
    @classmethod
    def _no_transferable_stakes(cls, v: bool) -> bool:
        if v:
            raise ValueError(
                "transferable stakes are forbidden: membership is soulbound"
            )
        return v

    @field_validator("voting_rule")
    @classmethod
    def _known_voting_rule(cls, v: str) -> str:
        if v not in ("binary", "plurality", "approval"):
            raise ValueError(
                f"unknown voting rule: {v!r} (binary|plurality|approval)"
            )
        return v
