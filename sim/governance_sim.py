"""Agent-based governance simulator for commonchain (overnight batch).

Simulates collectives of N members voting on sequences of proposals under
honest / apathetic / adversarial behaviour. Every run uses the REAL engine
(Collective.propose + evaluate): no reimplementation of tallying, so the
sweep measures the shipped code, not a model of it.

Agent types
-----------
* honest:      votes yes with probability p_yes (sincere majority).
* apathetic:   abstains with probability p_abstain (turnout pathology).
* adversarial: coordinated bloc voting NO on good proposals / YES on hostile
  ones (vote-buying / capture resistance probe).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from commonchain.chain import Collective
from commonchain.governance import Ballot
from commonchain.models import Charter, Member


@dataclass
class SimConfig:
    n_members: int = 9
    quorum_pct: float = 50.0
    pass_pct: float = 50.0
    supermajority_pct: float = 66.0
    adversarial_frac: float = 0.0
    apath_frac: float = 0.0
    p_yes: float = 0.6
    p_abstain: float = 0.8
    n_proposals: int = 20
    seed: int = 0


@dataclass
class SimResult:
    n_proposals: int = 0
    n_passed: int = 0
    n_deadlocked: int = 0
    n_quorum_fail: int = 0
    n_adversarial_wins: int = 0
    _turnout_sum: float = 0.0

    @property
    def turnout_mean(self) -> float:
        """Mean ballot-cast rate per proposal.

        This is the variable quorum acts on; without it a flat
        ``quorum_fail_rate`` cannot be distinguished from a quorum that was
        never in reach.
        """
        return self._turnout_sum / self.n_proposals if self.n_proposals else 0.0

    @property
    def pass_rate(self) -> float:
        return self.n_passed / self.n_proposals if self.n_proposals else 0.0

    @property
    def deadlock_rate(self) -> float:
        return self.n_deadlocked / self.n_proposals if self.n_proposals else 0.0

    @property
    def quorum_fail_rate(self) -> float:
        return self.n_quorum_fail / self.n_proposals if self.n_proposals else 0.0

    @property
    def adversarial_win_rate(self) -> float:
        return (
            self.n_adversarial_wins / self.n_proposals if self.n_proposals else 0.0
        )


def _build_collective(cfg: SimConfig) -> Collective:
    charter = Charter.model_validate(
        {
            "name": "sim",
            "mission": "simulation collective",
            "quorum_pct": cfg.quorum_pct,
            "pass_pct": cfg.pass_pct,
            "supermajority_pct": cfg.supermajority_pct,
        }
    )
    members = [Member(address=f"0x{i:04x}") for i in range(cfg.n_members)]
    return Collective.from_charter(charter, members)


def run_collective(cfg: SimConfig) -> SimResult:
    """Simulate one collective living through n_proposals decisions."""
    rng = random.Random(cfg.seed)
    col = _build_collective(cfg)
    addrs = [m.address for m in col.active_members()]

    n_adv = int(round(cfg.n_members * cfg.adversarial_frac))
    n_apath = int(round((cfg.n_members - n_adv) * cfg.apath_frac))
    adv = set(rng.sample(addrs, n_adv)) if n_adv else set()
    rest = [a for a in addrs if a not in adv]
    apath = set(rng.sample(rest, min(n_apath, len(rest)))) if n_apath else set()

    res = SimResult()
    for i in range(cfg.n_proposals):
        # Alternate good proposals (honest YES) and hostile ones (adv YES).
        hostile = (i % 4 == 3) and bool(adv)
        ballots: list[Ballot] = []
        for a in addrs:
            if a in apath and rng.random() < cfg.p_abstain:
                continue  # abstention: no ballot cast
            if a in adv:
                ballots.append(Ballot(voter=a, yes=hostile))
            else:
                ballots.append(
                    Ballot(voter=a, yes=(rng.random() < (0.15 if hostile else cfg.p_yes)))
                )
        block = col.propose(f"proposal-{i}", ballots)
        res.n_proposals += 1
        res._turnout_sum += len(ballots) / cfg.n_members
        if block.tally.passed:
            res.n_passed += 1
            if hostile:
                res.n_adversarial_wins += 1
        elif not block.tally.quorum_met:
            res.n_quorum_fail += 1
        else:
            res.n_deadlocked += 1
    assert col.verify(), "chain integrity broke during simulation"
    return res


def run_payroll_cell(
    policy: str,
    stable_base_share: float,
    n: int,
    hours_dist: str,
    seed: int,
    pool: float = 1000.0,
) -> dict:
    """One payroll fairness cell. Returns gini, floor-violation rate, shares."""
    from commonchain.modules import payroll as payroll_mod

    rng = random.Random(seed)
    charter = Charter.model_validate(
        {
            "name": "pay-sim",
            "mission": "payroll simulation",
            "modules": {
                "payroll": {"policy": policy, "stable_base_share": stable_base_share}
            },
        }
    )
    if hours_dist == "uniform":
        hours = [rng.uniform(5, 40) for _ in range(n)]
    elif hours_dist == "pareto":
        hours = [rng.paretovariate(1.5) * 10 for _ in range(n)]
    else:  # bimodal: core full-timers + peripheral contributors
        hours = [
            rng.uniform(30, 40) if rng.random() < 0.3 else rng.uniform(1, 8)
            for _ in range(n)
        ]
    members = [
        Member(address=f"0x{i:04x}", metrics={"labor_hours": h})
        for i, h in enumerate(hours)
    ]
    col = Collective.from_charter(charter, members)
    shares = payroll_mod.distribute(col, pool)
    vals = sorted(shares.values())
    # Gini coefficient.
    gini = (
        sum((2 * (i + 1) - len(vals) - 1) * v for i, v in enumerate(vals))
        / (len(vals) * sum(vals))
        if sum(vals) else 0.0
    )
    floor = pool * stable_base_share / n
    floor_viol = sum(1 for v in vals if v < floor - 1e-9) / len(vals)
    return {
        "policy": policy,
        "stable_base_share": stable_base_share,
        "n": n,
        "hours_dist": hours_dist,
        "seed": seed,
        "gini": gini,
        "floor_violation_rate": floor_viol,
        "min_share": min(vals),
        "max_share": max(vals),
    }


def run_mandate_cell(
    n_members: int, term_blocks: int, seed: int, n_rounds: int = 30
) -> dict:
    """Mandate rotation cell. Returns concentration + lapse metrics."""
    rng = random.Random(seed)
    col = _build_collective(SimConfig(n_members=n_members))
    addrs = [m.address for m in col.active_members()]
    holder_counts: dict[str, int] = {a: 0 for a in addrs}
    n_lapsed = 0
    n_granted = 0
    for r in range(n_rounds):
        assignee = rng.choice(addrs)
        voters = rng.sample(addrs, k=max(1, int(len(addrs) * 0.7)))
        ballots = [Ballot(voter=a, yes=True) for a in voters]
        try:
            block = col.propose(
                f"mandate-{r}",
                ballots,
                kind="mandate",
                payload={
                    "assignee": assignee,
                    "role": "facilitator",
                    "scope": "coordination",
                    "term_blocks": term_blocks,
                },
            )
        except Exception:
            continue
        if block.tally.passed:
            n_granted += 1
            holder_counts[assignee] += 1
        n_lapsed += sum(
            1 for m in col.mandates if m["expires_at_block"] == len(col.chain)
        )
    total = sum(holder_counts.values()) or 1
    # Herfindahl concentration: 1/n = perfectly rotated, 1.0 = one boss.
    hhi = sum((c / total) ** 2 for c in holder_counts.values())
    return {
        "n_members": n_members,
        "term_blocks": term_blocks,
        "seed": seed,
        "n_granted": n_granted,
        "hhi_concentration": hhi,
        "n_lapsed": n_lapsed,
    }
