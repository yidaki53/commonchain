"""Night 3, Job 2: template fuzz.

Every shipped charter kind (coop/party/movement/club/generic) survives 100
random decisions -- ordinary business under its own voting rule, membership
votes, rotating mandates, and hostile amendments against the immutable core --
with the chain intact and zero unexpected errors. Loads the YAML templates
exactly as `commonchain init` does, so schema drift in any template is caught
here rather than by a user.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective, GovernanceError  # noqa: E402
from commonchain.governance import Ballot  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

TEMPLATES = ROOT / "commonchain" / "templates"


def _yes_ballots(col: Collective, voters: list[str]) -> tuple[list[Ballot], list[str]]:
    """Ballots that pass under the collective's own voting rule."""
    if col.charter.voting_rule == "binary":
        return [Ballot(voter=a, yes=True) for a in voters], []
    opts = ["opt0", "opt1"]
    return [Ballot(voter=a, choices=["opt0"]) for a in voters], opts


def fuzz_kind(kind: str, n_rounds: int = 100, seed: int = 7) -> dict:
    rng = random.Random(seed)
    raw = (TEMPLATES / f"charter.{kind}.yaml").read_text().replace(
        "{{ org_name }}", "Fuzz Collective"
    )
    charter = Charter.model_validate(yaml.safe_load(raw))
    members = [Member(address=f"0x{i:04x}") for i in range(5)]
    col = Collective.from_charter(charter, members)

    counters = {
        "general": 0,
        "onboard": 0,
        "mandate": 0,
        "amend_blocked": 0,
        "errors": 0,
    }
    extra = 0
    for r in range(n_rounds):
        active = [m.address for m in col.active_members()]
        if not active:
            col.add_member(Member(address=f"0x9{extra:03x}"))
            extra += 1
            active = [m.address for m in col.active_members()]
        voters = rng.sample(active, k=max(1, int(len(active) * 0.7)))
        roll = rng.random()
        try:
            if roll < 0.60:  # ordinary business under the charter's own rule
                if charter.voting_rule == "binary":
                    ballots = [
                        Ballot(voter=a, yes=rng.random() < 0.6) for a in voters
                    ]
                    col.propose(f"biz-{r}", ballots)
                else:
                    opts = [f"opt{j}" for j in range(3)]
                    ballots = [
                        Ballot(voter=a, choices=[rng.choice(opts)])
                        for a in voters
                    ]
                    col.propose(f"biz-{r}", ballots, options=opts)
                counters["general"] += 1
            elif roll < 0.75 and len(active) < 8:
                ballots, opts = _yes_ballots(col, voters)
                col.propose(
                    f"onboard-{r}",
                    ballots,
                    kind="membership",
                    payload={
                        "action": "add",
                        "member": {"address": f"0xe{extra:03x}"},
                    },
                    options=opts,
                )
                extra += 1
                counters["onboard"] += 1
            elif roll < 0.90:
                ballots, opts = _yes_ballots(col, voters)
                col.propose(
                    f"mandate-{r}",
                    ballots,
                    kind="mandate",
                    payload={
                        "assignee": rng.choice(active),
                        "role": "captain",
                        "scope": "fuzz",
                        "term_blocks": rng.randint(1, 5),
                    },
                    options=opts,
                )
                counters["mandate"] += 1
            else:  # hostile core amendments must ALWAYS raise
                ballots, opts = _yes_ballots(col, voters)
                field = rng.choice(
                    ["one_member_one_vote", "stakes_transferable"]
                )
                col.propose(
                    f"hostile-{r}",
                    ballots,
                    kind="charter_amendment",
                    payload={"charter": {field: True}},
                    options=opts,
                )
                counters["errors"] += 1  # reaching pass = core was breached
        except GovernanceError:
            counters["amend_blocked"] += 1
        except ValueError:
            counters["errors"] += 1
        if r % 10 == 0:
            assert col.verify(), f"{kind}: chain broken at round {r}"

    assert col.verify(), f"{kind}: chain broken at end"
    assert counters["errors"] == 0, f"{kind}: unexpected errors: {counters}"
    return {
        "kind": kind,
        "rounds": n_rounds,
        **counters,
        "chain_len": len(col.chain),
        "charter_version": col.charter_version,
    }


def main() -> None:
    kinds = sorted(
        p.name.split(".")[1] for p in TEMPLATES.glob("charter.*.yaml")
    )
    print(f"[template_fuzz] kinds: {kinds}", flush=True)
    for kind in kinds:
        stats = fuzz_kind(kind)
        print(f"[template_fuzz] {kind}: {stats}", flush=True)
    print("[template_fuzz] ALL TEMPLATES OK", flush=True)


if __name__ == "__main__":
    main()
