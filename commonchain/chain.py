"""The Collective engine: members and the hash-linked decision chain.

``Collective`` is the runtime object any organisation instantiates -- a co-op,
a party, a movement, a hobby club, a volunteer network. It owns the charter
(genesis), the member registry (soulbound memberships) and the append-only
decision chain. It is deliberately chain-agnostic: the Python engine here is
the reference implementation and the source of truth for tests and
simulations; the Solidity contracts under ``contracts/`` mirror it on-chain.

The core knows nothing about money, dues or disputes. Those are optional
modules under ``commonchain.modules``, configured in ``Charter.modules``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .governance import Ballot, DecisionBlock, Proposal, Tally, evaluate
from .models import Charter, Member, hash_model


class GovernanceError(Exception):
    """Raised when an action violates the charter or chain invariants."""


@dataclass
class Collective:
    """A self-governing, member-owned collective.

    Invariants enforced here (and mirrored on-chain in ``contracts/test``):
      * ownership stakes are non-transferable (there is no transfer API);
      * voting power is never bought, sold or delegated: every active member's
        vote weight is exactly 1;
      * the chain is the complete institutional memory, append-only and
        hash-linked back to the charter.

    Money (if any) is handled by optional modules, not by this class.
    """

    charter: Charter
    members: dict[str, Member] = field(default_factory=dict)
    chain: list[DecisionBlock] = field(default_factory=list)
    # Granted coordination mandates (rotating facilitators, not bosses).
    mandates: list[dict] = field(default_factory=list)
    # Constitutional history: every charter version, starting with genesis.
    # Block #k records which version it was decided under, so amendments
    # never invalidate earlier history.
    charter_history: list[Charter] = field(default_factory=list)

    @property
    def charter_version(self) -> int:
        return len(self.charter_history)

    # ---- genesis ---------------------------------------------------------
    @classmethod
    def from_charter(
        cls, charter: Charter, founders: Iterable[Member]
    ) -> "Collective":
        col = cls(charter=charter)
        col.charter_history.append(charter.model_copy(deep=True))
        for m in founders:
            col.add_member(m)
        return col

    @property
    def genesis_hash(self) -> str:
        """The genesis block hash is the canonical hash of the charter."""
        return hash_model(self.charter)

    @property
    def head_hash(self) -> str:
        if not self.chain:
            return self.genesis_hash
        return self.chain[-1].block_hash

    # ---- membership (soulbound) -----------------------------------------
    def add_member(self, member: Member) -> None:
        if member.address in self.members:
            raise GovernanceError(f"member already exists: {member.address}")
        self.members[member.address] = member

    def deactivate_member(self, address: str) -> None:
        addr = address.lower()
        if addr not in self.members:
            raise GovernanceError(f"unknown member: {addr}")
        # Offboarding sets active=False; the stake is *burned*, never moved to
        # another member -- there is deliberately no transfer_stake() method.
        self.members[addr].active = False

    def active_members(self) -> list[Member]:
        return [m for m in self.members.values() if m.active]

    # NOTE: there is intentionally no `transfer_stake(a, b)` method. Ownership
    # is soulbound; the only mutations are add (onboarding) and deactivate
    # (offboarding). This is what makes "equity non-transferable" a structural
    # property rather than a policy we merely intend to follow.

    # ---- decision chain --------------------------------------------------
    def propose(
        self,
        title: str,
        ballots: Iterable[Ballot],
        *,
        kind: str = "general",
        description: str = "",
        payload: Optional[dict] = None,
        options: Optional[list[str]] = None,
    ) -> DecisionBlock:
        """Vote on a proposal and, regardless of outcome, append the record.

        Failed proposals are still appended: the chain is the *complete*
        institutional memory, not only the record of what succeeded. Domain
        effects (membership changes, charter amendments) apply on pass; other
        business decisions are executed by humans and merely *ratified* here.
        ``options`` lists the allowed choices for plurality/approval rules.
        """

        proposal = Proposal(
            title=title,
            description=description,
            kind=kind,
            options=list(options or []),
            payload=payload or {},
        )
        tally = evaluate(self.charter, self.members.values(), proposal, ballots)
        block = self._append(tally)
        if block.tally.passed:
            self._apply_effects(block)
        return block

    def _apply_effects(self, block: DecisionBlock) -> None:
        """Execute a passed decision's side effects.

        This is the piece that makes the chain more than a log -- and the piece
        that makes the managerial class redundant. Every management function is
        a vote-gated effect:

        * ``charter_amendment`` -- policy changes (the old "executive memo"),
          mutating the amendable policy layer. The immutable democratic core
          (``one_member_one_vote``, ``stakes_transferable``) is never amendable.
          Nested module config uses dotted paths, e.g.
          ``{"modules.payroll.policy": "labor_hours"}``, so one module's update
          never wipes a sibling module's config.
        * ``membership`` -- onboarding/offboarding without an HR department:
          ``payload={"action": "add"|"remove", ...}``.
        * ``mandate`` -- role/task assignment without a boss: a member is
          granted a named, scoped, time-limited mandate
          (``payload={"assignee": ..., "role": ..., "scope": ...,
          "term_blocks": N}``). Mandates confer coordination duties, never
          ownership or extra votes, and they expire automatically -- the
          Foss & Klein "hierarchy never fully dies" fallback (rotating
          facilitators, not bosses).

        Unknown kinds are still recorded on-chain but have no code effect; most
        business decisions are executed by humans and merely *ratified* here.
        """

        kind = block.tally.proposal.kind
        payload = block.tally.proposal.payload
        if kind == "charter_amendment":
            self._amend_charter(payload.get("charter", {}))
        elif kind == "membership":
            self._apply_membership(payload)
        elif kind == "mandate":
            self._apply_mandate(payload, block.index)

    # The democratic floor is not amendable by any vote. Enforcing this in code
    # (not just in the charter text) is what stops a hostile majority from
    # voting itself into shareholder-style control.
    IMMUTABLE_CORE = ("one_member_one_vote", "stakes_transferable")

    def _amend_charter(self, changes: dict) -> None:
        # Split dotted module paths ("modules.payroll.policy") from top-level
        # charter fields, so updating one module never wipes sibling modules.
        top_level: dict = {}
        module_updates: dict[str, dict] = {}
        for key, value in changes.items():
            parts = key.split(".")
            if parts[0] == "modules" and len(parts) == 3:
                module_updates.setdefault(parts[1], {})[parts[2]] = value
            else:
                top_level[key] = value

        illegal = sorted(set(top_level) & set(self.IMMUTABLE_CORE))
        if illegal:
            raise GovernanceError(
                f"cannot amend the immutable democratic core: {', '.join(illegal)}"
            )
        # Re-validate through Charter so ranges/enums stay enforced.
        merged = self.charter.model_dump(mode="json")
        merged.update(top_level)
        modules = dict(merged.get("modules") or {})
        for module_name, updates in module_updates.items():
            modules[module_name] = {**(modules.get(module_name) or {}), **updates}
        merged["modules"] = modules
        self.charter = Charter.model_validate(merged)
        # Snapshot the new constitutional version. History is append-only:
        # earlier blocks keep pointing at earlier versions and stay valid.
        self.charter_history.append(self.charter.model_copy(deep=True))

    def _apply_membership(self, payload: dict) -> None:
        action = payload.get("action")
        if action == "add":
            self.add_member(Member.model_validate(payload.get("member", {})))
        elif action == "remove":
            self.deactivate_member(payload["address"])
        else:
            raise GovernanceError(f"unknown membership action: {action!r}")

    def _apply_mandate(self, payload: dict, block_index: int) -> None:
        """Grant a time-limited coordination mandate (no boss powers).

        A mandate names an assignee, a role, a scope and an expiry measured in
        decision blocks. On expiry the mandate is inert; renewal needs a fresh
        vote. The assignee must be an active member, and the mandate grants no
        ownership, no extra votes and no unilateral powers -- coordination
        duties only. This is how the package absorbs the skeptics' point
        (Foss & Klein: hierarchy never fully dies) without recreating bosses:
        rotating, revocable, expiring facilitators.
        """
        assignee = str(payload.get("assignee", "")).lower()
        role = str(payload.get("role", "")).strip()
        if not role:
            raise GovernanceError("mandate requires a named role")
        if assignee not in self.members or not self.members[assignee].active:
            raise GovernanceError(f"mandate assignee is not an active member: {assignee}")
        try:
            term_blocks = int(payload.get("term_blocks", 0))
        except (TypeError, ValueError):
            raise GovernanceError("mandate term_blocks must be an integer")
        if term_blocks <= 0:
            raise GovernanceError("mandate term_blocks must be positive")
        self.mandates.append(
            {
                "role": role,
                "assignee": assignee,
                "scope": str(payload.get("scope", "")),
                "granted_at_block": block_index,
                "expires_at_block": block_index + term_blocks,
            }
        )

    def active_mandates(self) -> list[dict]:
        """Mandates that have not yet expired (current chain height = len)."""
        height = len(self.chain)
        return [
            m for m in self.mandates if m["expires_at_block"] > height
        ]

    def _append(self, tally: Tally) -> DecisionBlock:
        # Stamp the charter version the vote was decided UNDER (pre-effect).
        # The amendment effect then snapshots the new version for later blocks.
        block = DecisionBlock(
            index=len(self.chain),
            timestamp=tally.proposal.created_at,
            prev_hash=self.head_hash,
            tally=tally,
            charter_hash=hash_model(self.charter_history[-1]),
            charter_version=self.charter_version - 1,
        )
        block.block_hash = block.compute_hash()
        self.chain.append(block)
        return block

    # ---- integrity -------------------------------------------------------
    def verify(self) -> bool:
        """Recompute every hash and check linkage + constitutional versions.

        Each block's prev_hash must chain correctly AND its charter_hash must
        match the charter version recorded in history. This is what lets the
        charter evolve: old blocks stay valid under the version they were
        decided under, instead of all breaking when policy changes.
        """
        if not self.charter_history:
            return False
        prev = hash_model(self.charter_history[0])
        for block in self.chain:
            if block.prev_hash != prev:
                return False
            if block.charter_version >= len(self.charter_history):
                return False
            if block.charter_hash != hash_model(
                self.charter_history[block.charter_version]
            ):
                return False
            if block.compute_hash() != block.block_hash:
                return False
            prev = block.block_hash
        return True

    def verify_block(self, index: int) -> bool:
        """Verify a single block plus its linkage to both neighbours.

        O(1): recomputes ``compute_hash()`` and checks ``prev_hash`` against
        the predecessor (or genesis for block 0), ``block_hash`` against the
        recomputation, ``charter_hash`` against ``charter_history``, and the
        successor's ``prev_hash`` against this block's stored hash. Returns
        True iff the tampered neighbourhood is self-consistent.
        """
        if index < 0 or index >= len(self.chain):
            return False
        block = self.chain[index]
        if block.compute_hash() != block.block_hash:
            return False
        if block.charter_version >= len(self.charter_history):
            return False
        if block.charter_hash != hash_model(
            self.charter_history[block.charter_version]
        ):
            return False
        expected_prev = (
            self.genesis_hash if index == 0 else self.chain[index - 1].block_hash
        )
        if block.prev_hash != expected_prev:
            return False
        if index + 1 < len(self.chain) and (
            self.chain[index + 1].prev_hash != block.block_hash
        ):
            return False
        return True

    def audit_trail(self) -> list[dict]:
        """A compact, human-readable view of the collective's evolution."""
        return [
            {
                "index": b.index,
                "title": b.tally.proposal.title,
                "kind": b.tally.proposal.kind,
                "passed": b.tally.passed,
                "yes": b.tally.yes,
                "no": b.tally.no,
                "winner": b.tally.winner,
                "tie": b.tally.tie,
                "voting_rule": b.tally.voting_rule,
                "quorum_met": b.tally.quorum_met,
                "hash": b.block_hash,
                "prev_hash": b.prev_hash,
            }
            for b in self.chain
        ]
