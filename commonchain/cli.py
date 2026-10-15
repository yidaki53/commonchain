"""Command-line interface for commonchain.

A 3-person collective can instantiate itself and start making managerial
decisions in minutes, entirely offline / on testnet. Nothing here talks to a
mainnet and no secrets are required for the local/offline workflow.

There is no manager role: hiring/firing (member), role assignment (mandate),
policy changes (amend) and every other decision are proposals the members vote
on. The chain records and executes them.

Commands:
    init      create a new collective (genesis charter + member registry)
    member    add / list members (soulbound)
    propose   vote on a proposal and append a decision block
    mandates  list live coordination mandates (rotating, expiring, revocable)
    pay       distribute revenue (optional payroll module)
    audit     print the hash-linked decision trail and verify integrity
    export    dump the chain + charter as JSON for archiving
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml

from .chain import Collective
from .governance import Ballot, DecisionBlock
from .models import Charter, Member

app = typer.Typer(
    add_completion=False,
    help="FOSS self-governance: charter = genesis, management = vote-gated blocks.",
    no_args_is_help=True,
)

STATE_FILE = "collective.json"
TEMPLATES = Path(__file__).parent / "templates"


def _load_collective(directory: Path) -> Collective:
    state_path = directory / STATE_FILE
    if not state_path.exists():
        raise typer.BadParameter(
            f"no collective found in {directory}. Run `commonchain init` first."
        )
    data = json.loads(state_path.read_text())
    col = Collective(
        charter=Charter.model_validate(_migrate_charter(data["charter"])),
        members={
            a: Member.model_validate(m) for a, m in data["members"].items()
        },
    )
    col.chain = [
        DecisionBlock.model_validate(b) for b in data.get("chain", [])
    ]
    col.mandates = list(data.get("mandates", []))
    # charter_history persisted since the versioning fix; older states rebuild
    # it as [genesis] (blocks stamped post-fix carry explicit versions).
    if data.get("charter_history"):
        col.charter_history = [
            Charter.model_validate(_migrate_charter(c))
            for c in data["charter_history"]
        ]
        # Current charter is the latest version.
        col.charter = col.charter_history[-1].model_copy(deep=True)
    else:
        col.charter_history = [col.charter.model_copy(deep=True)]
    return col


def _migrate_charter(raw: dict) -> dict:
    """Upgrade charters saved by earlier versions to the current schema.

    Older charters stored payroll/dispute fields top-level (``profit_split``,
    ``stable_base_share``, ``dispute_mode``). The refactor moved them under
    ``modules``. Migration preserves their values so existing collectives do
    not silently change meaning.
    """
    raw = dict(raw)
    modules = dict(raw.get("modules") or {})

    # v0.1 rename: worker-framed core field -> domain-neutral name. Old saved
    # states keep their meaning; new charters use the neutral name.
    if "one_worker_one_vote" in raw:
        raw["one_member_one_vote"] = raw.pop("one_worker_one_vote")

    legacy_payroll: dict = {}
    if "profit_split" in raw:
        legacy_payroll["policy"] = raw.pop("profit_split")
    if "stable_base_share" in raw:
        legacy_payroll["stable_base_share"] = raw.pop("stable_base_share")
    if legacy_payroll:
        modules["payroll"] = {**legacy_payroll, **modules.get("payroll", {})}
    if "dispute_mode" in raw:
        mode = raw.pop("dispute_mode")
        if "dispute" not in modules:
            modules["dispute"] = {"mode": mode}
    raw["modules"] = modules
    raw.pop("treasury", None)
    return raw


def _save_collective(col: Collective, directory: Path) -> None:
    state_path = directory / STATE_FILE
    data = {
        "charter": col.charter.model_dump(mode="json"),
        "charter_history": [c.model_dump(mode="json") for c in col.charter_history],
        "members": {a: m.model_dump(mode="json") for a, m in col.members.items()},
        "chain": [b.model_dump(mode="json") for b in col.chain],
        "mandates": col.mandates,
        "genesis_hash": col.genesis_hash,
    }
    state_path.write_text(json.dumps(data, indent=2))


@app.command()
def init(
    name: str = typer.Option(..., "--name", "-n", help="Collective name."),
    kind: str = typer.Option(
        "coop", "--kind", "-k", help="coop|party|movement|club|generic"
    ),
    jurisdiction: str = typer.Option(
        "generic", "--jurisdiction", "-j", help="legal wrapper module id"
    ),
    directory: Path = typer.Option(
        Path("."), "--dir", "-d", help="Where to write collective.json"
    ),
) -> None:
    """Create a new collective: the charter is the genesis block."""

    template_path = TEMPLATES / f"charter.{kind}.yaml"
    if not template_path.exists():
        raise typer.BadParameter(f"unknown kind '{kind}' (no {template_path.name})")
    raw = template_path.read_text().replace("{{ org_name }}", name)
    charter_data = yaml.safe_load(raw)
    charter_data["jurisdiction_module"] = jurisdiction
    charter = Charter.model_validate(charter_data)

    directory.mkdir(parents=True, exist_ok=True)
    col = Collective(charter=charter)
    _save_collective(col, directory)
    typer.echo(f"Initialised '{name}' ({kind}).")
    typer.echo(f"Genesis (charter) hash: {col.genesis_hash}")
    typer.echo(f"State written to {directory / STATE_FILE}")


@app.command()
def member(
    action: str = typer.Argument(..., help="add | list"),
    address: Optional[str] = typer.Argument(None, help="member wallet/identity"),
    display_name: str = typer.Option("", "--name", help="display name"),
    hours: float = typer.Option(
        0.0, "--hours", help="initial labour hours (shorthand for the metric)"
    ),
    metric: list[str] = typer.Option(
        [],
        "--metric",
        help="contribution metric as KEY=VALUE (e.g. attendance=12); repeatable",
    ),
    directory: Path = typer.Option(Path("."), "--dir", "-d"),
) -> None:
    """Add or list soulbound members."""

    col = _load_collective(directory)
    if action == "add":
        if not address:
            raise typer.BadParameter("address is required for 'add'")
        metrics: dict[str, float] = {}
        if hours:
            metrics["labor_hours"] = hours
        for spec in metric:
            key, _, value = spec.partition("=")
            key = key.strip()
            if not key or not value:
                raise typer.BadParameter(f"--metric must be KEY=VALUE, got {spec!r}")
            try:
                metrics[key] = float(value)
            except ValueError:
                raise typer.BadParameter(f"--metric value must be numeric: {spec!r}")
        col.add_member(
            Member(address=address, display_name=display_name, metrics=metrics)
        )
        _save_collective(col, directory)
        typer.echo(
            f"Added member {address}. Active members: {len(col.active_members())}"
        )
    elif action == "list":
        for m in col.members.values():
            state = "active" if m.active else "inactive"
            metrics_txt = (
                " ".join(f"{k}={v:g}" for k, v in sorted(m.metrics.items())) or "-"
            )
            typer.echo(
                f"  {m.address}  {m.display_name}  [{state}]  metrics: {metrics_txt}"
            )
    else:
        raise typer.BadParameter("action must be 'add' or 'list'")


@app.command()
def propose(
    title: str = typer.Argument(..., help="proposal title"),
    yes: str = typer.Option("", "--yes", help="comma-separated addresses voting yes"),
    no: str = typer.Option("", "--no", help="comma-separated addresses voting no"),
    kind: str = typer.Option(
        "general",
        "--kind",
        help="general|charter_amendment|membership|mandate|payroll",
    ),
    amend: Optional[str] = typer.Option(
        None,
        "--amend",
        help=(
            "charter amendment as JSON, e.g. "
            "'{\"modules.payroll.policy\": \"labor_hours\"}'"
        ),
    ),
    onboard: Optional[str] = typer.Option(
        None,
        "--onboard",
        help="address of a new member to onboard (membership kind)",
    ),
    offboard: Optional[str] = typer.Option(
        None,
        "--offboard",
        help="address of a member to offboard (membership kind)",
    ),
    mandate: Optional[str] = typer.Option(
        None,
        "--mandate",
        help=(
            "grant a rotating mandate, ADDRESS:ROLE -- "
            "coordination duties, never boss powers"
        ),
    ),
    mandate_scope: str = typer.Option(
        "", "--scope", help="scope of the mandate being granted"
    ),
    mandate_term: int = typer.Option(
        10, "--term", help="mandate length in decision blocks before expiry"
    ),
    options: str = typer.Option(
        "",
        "--options",
        help="comma-separated choices for plurality/approval votes (e.g. 'route A,route B,route C')",
    ),
    choice: list[str] = typer.Option(
        [],
        "--choice",
        help="ADDR:CHOICE ballot for plurality/approval votes; repeat (approval: repeat an addr for multiple choices)",
    ),
    directory: Path = typer.Option(Path("."), "--dir", "-d"),
) -> None:
    """Vote and append a decision block (passed or not, it is recorded).

    This is how management happens here: onboarding (``--onboard``),
    offboarding (``--offboard``), role assignment (``--mandate``) and policy
    changes (``--amend``) are all proposals the members vote on. No boss signs
    off. Under the binary rule use ``--yes``/``--no``; under plurality or
    approval rules use ``--options`` plus one ``--choice ADDR:CHOICE`` per
    ballot.
    """

    col = _load_collective(directory)
    rule = col.charter.voting_rule
    ballots: list[Ballot] = []
    for a in [s.strip() for s in yes.split(",") if s.strip()]:
        ballots.append(Ballot(voter=a, yes=True))
    for a in [s.strip() for s in no.split(",") if s.strip()]:
        ballots.append(Ballot(voter=a, yes=False))

    # Plurality/approval ballots: merge repeated addresses into one ballot
    # (approval voters approve several options with a single ballot).
    by_voter: dict[str, list[str]] = {}
    for spec in choice:
        addr, _, ch = spec.partition(":")
        addr, ch = addr.strip().lower(), ch.strip()
        if not addr or not ch:
            raise typer.BadParameter(f"--choice must be ADDR:CHOICE, got {spec!r}")
        by_voter.setdefault(addr, []).append(ch)
    if by_voter and (yes or no):
        raise typer.BadParameter(
            "cannot mix --yes/--no with --choice: pick one ballot style"
        )
    if by_voter and rule == "binary":
        raise typer.BadParameter(
            "--choice needs voting_rule plurality|approval "
            "(this collective is binary; use --yes/--no)"
        )
    if (yes or no) and rule != "binary":
        raise typer.BadParameter(
            f"--yes/--no are binary ballots (this collective uses {rule}); "
            "use --options and --choice"
        )
    for addr, chs in by_voter.items():
        ballots.append(Ballot(voter=addr, choices=chs))

    option_list = [s.strip() for s in options.split(",") if s.strip()]

    payload: dict = {}
    if amend:
        payload["charter"] = json.loads(amend)
        kind = "charter_amendment"
    elif onboard:
        payload = {
            "action": "add",
            "member": {"address": onboard, "display_name": onboard},
        }
        kind = "membership"
    elif offboard:
        payload = {"action": "remove", "address": offboard}
        kind = "membership"
    elif mandate:
        assignee, _, role = mandate.partition(":")
        payload = {
            "assignee": assignee.strip(),
            "role": role.strip(),
            "scope": mandate_scope,
            "term_blocks": mandate_term,
        }
        kind = "mandate"

    block = col.propose(title, ballots, kind=kind, payload=payload,
                        options=option_list)
    _save_collective(col, directory)
    t = block.tally
    verdict = "PASSED" if t.passed else "FAILED"
    typer.echo(f"[{verdict}] {title}")
    typer.echo(
        f"  yes={t.yes} no={t.no} quorum_met={t.quorum_met} "
        f"threshold={t.threshold_used_pct}%"
    )
    if t.voting_rule != "binary":
        if t.tie:
            typer.echo("  TIE: no decision -- re-vote (ties are never broken silently)")
        elif t.winner is not None:
            typer.echo(
                f"  winner: {t.winner} ({t.winner_share_pct:.1f}% of ballots cast)"
            )
    typer.echo(f"  block #{block.index} hash={block.block_hash[:16]}...")
    if t.passed and payload:
        typer.echo("  effect applied")


@app.command()
def mandates(
    directory: Path = typer.Option(Path("."), "--dir", "-d"),
) -> None:
    """List live coordination mandates (rotating facilitators, not bosses)."""

    col = _load_collective(directory)
    live = col.active_mandates()
    if not live:
        typer.echo("No active mandates.")
        return
    for m in live:
        typer.echo(
            f"  {m['role']}: {m['assignee']} "
            f"(scope: {m.get('scope') or '-'}, "
            f"expires at block {m['expires_at_block']})"
        )


@app.command()
def pay(
    revenue: float = typer.Argument(..., help="revenue to distribute now"),
    directory: Path = typer.Option(Path("."), "--dir", "-d"),
) -> None:
    """Distribute revenue (payroll module; co-ops/companies only).

    A collective without the payroll module enabled (e.g. a party or a
    volunteer network) gets a clear error, not a silent zero split.
    """

    from .modules import payroll

    col = _load_collective(directory)
    shares = payroll.distribute(col, revenue)
    cfg = payroll.config(col)
    typer.echo(
        f"Distributing {revenue:.2f} among {len(shares)} active members "
        f"(policy={cfg['policy']}, "
        f"base_share={cfg['stable_base_share']}):"
    )
    for addr, amt in shares.items():
        typer.echo(f"  {addr}: {amt:.2f}")


@app.command()
def audit(
    directory: Path = typer.Option(Path("."), "--dir", "-d"),
) -> None:
    """Print the decision trail and verify chain integrity."""

    col = _load_collective(directory)
    typer.echo(f"Charter (genesis) hash: {col.genesis_hash}")
    for row in col.audit_trail():
        flag = "PASS" if row["passed"] else "FAIL"
        typer.echo(
            f"  #{row['index']} [{flag}] {row['title']} "
            f"({row['yes']}/{row['no']}) {row['hash'][:12]} -> "
            f"prev {row['prev_hash'][:12]}"
        )
    ok = col.verify()
    typer.echo(f"Chain integrity: {'OK' if ok else 'BROKEN'}")


@app.command(name="export")
def export_cmd(
    out: Path = typer.Argument(..., help="output JSON path"),
    directory: Path = typer.Option(Path("."), "--dir", "-d"),
) -> None:
    """Export charter + chain as a portable JSON archive."""

    col = _load_collective(directory)
    # The export archive includes the full constitutional history so any
    # third party can re-verify every block against the version it was decided
    # under, without trusting the exporter.
    data = {
        "charter": col.charter.model_dump(mode="json"),
        "charter_history": [c.model_dump(mode="json") for c in col.charter_history],
        "members": {a: m.model_dump(mode="json") for a, m in col.members.items()},
        "chain": [b.model_dump(mode="json") for b in col.chain],
        "mandates": col.mandates,
        "genesis_hash": col.genesis_hash,
    }
    out.write_text(json.dumps(data, indent=2))
    typer.echo(f"Exported to {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
