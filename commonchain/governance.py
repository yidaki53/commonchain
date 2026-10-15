"""Vote tallying and the hash-linked decision chain.

The chain is the collective's institutional memory: an append-only sequence of
``DecisionBlock`` records. A block is only admitted if its vote satisfies the
charter's quorum and pass thresholds. One-member-one-vote is enforced by
construction: each block's tally is keyed by member address and rejects
duplicate or non-member ballots.

Voting rules (``Charter.voting_rule``):

* ``binary``   -- yes/no ratification (the original rule, unchanged defaults).
* ``plurality``-- each ballot carries exactly one choice from
  ``proposal.options``; the unique top choice wins (e.g. club route/book/captain
  picks). A tie is recorded and blocks the decision; it must be re-voted.
* ``approval`` -- each ballot carries any subset of ``proposal.options``; the
  option approved by the most ballots wins. Same tie handling.

Plurality and approval are winner-takes-all on a unique leader plus quorum:
there is no absolute-majority requirement, but ``winner_share_pct`` records how
often the winner was a minority choice -- a quantity the simulations measure
rather than assume away. All rules keep weight pinned to 1.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from pydantic import BaseModel, model_validator

from .models import Charter, Member, canonical_json, sha256_hex

# The genesis predecessor hash: 32 zero bytes hex, mirroring Bitcoin's convention.
GENESIS_PREV_HASH = "0" * 64


class Ballot(BaseModel):
    """A single signed ballot cast by a member on a proposal.

    ``weight`` exists only for audit and is *always* 1 -- there is deliberately
    no path to weight a vote by token holdings, which would recreate
    shareholder plutocracy.

    ``choices`` is the generalized ballot: ``["yes"]``/``["no"]`` under the
    binary rule, or one (plurality) / many (approval) names from
    ``proposal.options``. ``yes`` is kept as constructor sugar for the binary
    rule and is normalized into ``choices`` at validation time.
    """

    voter: str
    yes: Optional[bool] = None
    choices: list[str] = []
    weight: int = 1
    signature: str = ""  # placeholder; real impl signs the proposal digest

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        # Normalizes the binary ``yes`` sugar into ``choices`` on the raw input
        # (mode="before"), so re-validation of an already-built Ballot -- e.g.
        # when nested inside a Tally -- sees the normalized form and passes.
        if isinstance(data, dict):
            if data.get("weight", 1) != 1:
                raise ValueError("vote weight must be 1 (one member one vote)")
            yes = data.get("yes")
            choices = list(data.get("choices") or [])
            if yes is not None:
                sugar = ["yes"] if yes else ["no"]
                # Accept an already-normalized ballot (our own dumps carry
                # both keys); reject only genuinely contradictory input.
                if choices and choices != sugar:
                    raise ValueError(
                        "contradictory ballot: 'choices' disagrees with 'yes'"
                    )
                choices = sugar
            if not choices:
                raise ValueError("ballot must carry at least one choice")
            if len(choices) != len(set(choices)):
                raise ValueError("duplicate choices on one ballot")
            data = dict(data)
            data["choices"] = choices
        return data


class Proposal(BaseModel):
    """A pending business decision to be voted on."""

    title: str
    description: str = ""
    kind: str = "general"  # general | payroll | membership | charter_amendment
    # Allowed choices for plurality/approval rules (empty for binary).
    options: list[str] = []
    payload: dict[str, Any] = {}
    created_at: float = 0.0

    @model_validator(mode="after")
    def _stamp(self) -> "Proposal":
        if not self.created_at:
            object.__setattr__(self, "created_at", time.time())
        return self


class Tally(BaseModel):
    """The evaluated outcome of a proposal vote."""

    proposal: Proposal
    ballots: list[Ballot]
    eligible_voters: int
    yes: int
    no: int
    # Per-option tallies for plurality/approval (empty under binary).
    option_counts: dict[str, int] = {}
    # Unique winning option for plurality/approval; None under binary, on a
    # tie, or when nobody voted. A tie is never silently broken.
    winner: Optional[str] = None
    tie: bool = False
    winner_share_pct: float = 0.0
    quorum_met: bool
    passed: bool
    is_charter_amendment: bool
    threshold_used_pct: float
    voting_rule: str = "binary"

    @model_validator(mode="after")
    def _no_double_vote(self) -> "Tally":
        voters = [b.voter for b in self.ballots]
        if len(voters) != len(set(voters)):
            raise ValueError("duplicate ballot: one member one vote")
        for b in self.ballots:
            if b.weight != 1:
                raise ValueError("vote weight must be 1")
        if self.tie and self.winner is not None:
            raise ValueError("contradictory tally: tie recorded with a winner")
        return self


class DecisionBlock(BaseModel):
    """An appended, hash-linked decision record.

    ``charter_hash`` snapshots the charter version this block was decided
    under. This is what makes amendments safe: block #k links to the genesis
    (or the charter version active at #k), so later amendments never
    invalidate earlier history. The chain records not just decisions but the
    constitutional version each decision was made under.
    """

    index: int
    timestamp: float
    prev_hash: str
    tally: Tally
    charter_hash: str = ""
    charter_version: int = 0
    # Filled after construction by Collective.append_decision.
    block_hash: str = ""

    def body_bytes(self) -> bytes:
        return canonical_json(self.model_dump(mode="json", exclude={"block_hash"}))

    def compute_hash(self) -> str:
        return sha256_hex(self.body_bytes())


def evaluate(
    charter: Charter,
    members: Iterable[Member],
    proposal: Proposal,
    ballots: Iterable[Ballot],
) -> Tally:
    """Tally ballots and decide whether a proposal passes.

    Enforces: eligible voters are *active members only*; weight is 1; quorum is
    a percentage of active members; charter amendments need a super-majority
    (binary rule; under plurality/approval an amendment needs a unique winner
    plus quorum, since supermajority does not map onto multi-option ballots).
    The rule itself comes from ``charter.voting_rule``.
    """

    active = [m for m in members if m.active]
    active_addrs = {m.address for m in active}
    ballots = list(ballots)

    for b in ballots:
        if b.voter not in active_addrs:
            raise ValueError(f"ballot from non-active member: {b.voter}")
        if b.weight != 1:
            raise ValueError("vote weight must be 1 (one member one vote)")

    rule = charter.voting_rule
    eligible = len(active)
    cast = len(ballots)
    turnout_pct = (cast / eligible * 100.0) if eligible else 0.0
    quorum_met = turnout_pct >= charter.quorum_pct

    is_amendment = proposal.kind == "charter_amendment"
    threshold = charter.supermajority_pct if is_amendment else charter.pass_pct

    if rule == "binary":
        for b in ballots:
            if b.choices not in (["yes"], ["no"]):
                raise ValueError("binary rule accepts only 'yes'/'no' ballots")
        yes = sum(1 for b in ballots if b.choices == ["yes"])
        no = cast - yes
        yes_pct = (yes / cast * 100.0) if cast else 0.0
        passed = quorum_met and cast > 0 and yes_pct >= threshold
        return Tally(
            proposal=proposal,
            ballots=ballots,
            eligible_voters=eligible,
            yes=yes,
            no=no,
            quorum_met=quorum_met,
            passed=passed,
            is_charter_amendment=is_amendment,
            threshold_used_pct=threshold,
            voting_rule=rule,
        )

    # ---- plurality / approval --------------------------------------------
    options = list(proposal.options)
    if not options:
        raise ValueError(f"{rule} rule requires a non-empty proposal.options")
    if len(options) != len(set(options)):
        raise ValueError("proposal.options contains duplicates")
    for b in ballots:
        if rule == "plurality" and len(b.choices) != 1:
            raise ValueError("plurality ballots must carry exactly one choice")
        for c in b.choices:
            if c not in options:
                raise ValueError(f"choice not among proposal options: {c!r}")

    counts = {o: sum(1 for b in ballots if o in b.choices) for o in options}
    top = max(counts.values()) if cast else 0
    leaders = [o for o, c in counts.items() if c == top]
    winner = leaders[0] if (top > 0 and len(leaders) == 1) else None
    tie = top > 0 and len(leaders) > 1
    share = (top / cast * 100.0) if cast else 0.0
    passed = quorum_met and cast > 0 and winner is not None

    return Tally(
        proposal=proposal,
        ballots=ballots,
        eligible_voters=eligible,
        yes=0,
        no=0,
        option_counts=counts,
        winner=winner,
        tie=tie,
        winner_share_pct=share,
        quorum_met=quorum_met,
        passed=passed,
        is_charter_amendment=is_amendment,
        threshold_used_pct=threshold,
        voting_rule=rule,
    )
