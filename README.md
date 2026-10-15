# commonchain

A FOSS self-governance core for worker-owned collectives, political parties and
movements. It uses hash-linked blockchain records to make managerial decisions
transparent, auditable and vote-gated — making the managerial class redundant.

The **charter is the genesis block**. Every subsequent business decision is a
signed, hash-linked, vote-gated block appended after a collective vote. The
chain *is* the organisation's institutional memory: immutable, auditable policy
evolution adapting to changing conditions. Smart-contract-style rules replace
managerial functions: proposals, voting, resource distribution, role
(mandate) assignment, onboarding/offboarding.

Core principles, enforced in code rather than promised in prose:

- **One member = one vote.** No token-weighted voting, no shareholder
  plutocracy. Ballots with weight != 1 are rejected at construction.
- **Soulbound ownership.** Stakes are non-transferable; there is deliberately
  no `transfer_stake()` API. Offboarding burns a stake, it never moves it.
- **Democratic floor is immutable.** `one_member_one_vote` and
  `stakes_transferable=false` cannot be changed by any vote — a hostile
  majority cannot vote itself into shareholder-style control.
- **Payroll is a module, not a feature.** Co-ops can enable profit splitting
  (`modules/payroll`); parties and volunteering organisations simply do not
  enable it. Nothing organisation-specific is hardcoded in the core.
- **Voting rules are pluggable.** Charters choose `binary` (yes/no
  ratification), `plurality` (decisive club default), or `approval`
  (expressive, needs revote-friendly culture) — all weight-1, all
  vote-gated, all hash-linked. Rule itself is amendable policy, not core.
- **Coordinators, not bosses.** Rotation mandates (`--term`) expire; short
  terms plus revocable delegation keep power circulating.

## Quickstart (uv)

```bash
uv sync                      # creates .venv, installs deps + package (editable)
uv run commonchain init --name "Bright Futures Co-op" --kind coop --dir ./demo
uv run commonchain member add 0xaaa --name Alice --dir ./demo
uv run commonchain member add 0xbbb --name Bob   --dir ./demo
uv run commonchain member add 0xccc --name Cara  --dir ./demo
uv run commonchain propose "Buy a 3D printer" --yes 0xaaa,0xbbb,0xccc --dir ./demo
uv run commonchain pay 1000 --dir ./demo         # distribute revenue (coop payroll module)
uv run commonchain audit --dir ./demo           # hash-linked trail + integrity check
```

Charter kinds: `coop` (company), `party`, `movement`, `club`, `generic`.
Jurisdiction wrapper modules are pluggable (`--jurisdiction uk|se|sce|generic`) —
see `docs/playbook/jurisdictions/`. The project ships a legal-wrapper playbook,
not legal advice.

## Repository layout

```
commonchain/
├── commonchain/           # Python package (chain-agnostic reference implementation)
│   ├── chain.py           # Collective engine: genesis, decision chain, effects
│   ├── governance.py      # Ballots, tallies, quorum/pass/supermajority rules
│   ├── models.py          # Charter (genesis), Member (soulbound stake)
│   ├── modules/           # Optional plug-ins: payroll, delegation, mandates
│   ├── templates/         # Charters: charter.coop / party / movement yaml
│   └── cli.py             # typer CLI: init, member, propose, pay, audit, export
├── contracts/             # Solidity mirrors (CharterGovernor, PayrollSplitter, ...)
├── sim/                   # Agent-based simulations + parameter sweeps
├── analysis/              # Aggregations, confidence intervals, figures
├── results/               # Tables, figures, findings (results/night2/ = CI sweeps)
├── docs/playbook/         # Chartering, decision protocol, jurisdictions, exit
├── tests/                 # Invariants: profits stay in worker set, equal votes,
│                          # non-transferable equity, tamper-evidence
└── run_overnight.sh       # Long-running sweep orchestrator (checkpointed)
```

## Development (uv only for this repo)

```bash
uv run python -m pytest tests/ -q --cov=commonchain   # full gate
uv run ruff check commonchain sim analysis tests      # lint
uv run python -m ruff check ...                       # same, via module form
uv run python analysis/make_figures.py                # regenerate figures
uv run commonchain --help                             # CLI
```

Simulation-validated defaults (see `results/OVERNIGHT_FINDINGS.md`,
`results/night2/`, `results/night3/`): `quorum_pct=50, pass_pct=50`,
`voting_rule=plurality` for clubs — raising quorum buys paralysis, not
legitimacy, because turnout (not thresholds) is the binding constraint.
Scale: 500k-block chain, full verify ~150s, 500/500 tampers caught.

## Radical honesty

What this package cannot do: adjudicate disputes beyond the pluggable
council/Kleros stub, replace tacit coordination, or manufacture trust.
Human fallback roles (rotating coordinators with expiry) are first-class
citizens, not an afterthought.

## License

AGPL-3.0-or-later. Self-hostable, everything FOSS.

## Citation

```bibtex
@software{commonchain,
  title  = {commonchain: blockchain self-governance for worker-owned collectives},
  author = {Oberg, Robin},
  year   = {2026},
  note   = {FOSS (AGPL-3.0). Simulation findings in results/},
}
```
