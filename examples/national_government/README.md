# Commonwealth Republic — Nation on commonchain

## Overview

This example demonstrates how commonchain can serve as the operating system
for a national government:

* Citizens are members — one person, one vote.
* `voting_rule: approval` supports multi-option legislation.
* A `payroll` module manages civil-service compensation.
* A `delegation` module supports representative delegation for routine decisions.
* Charter amendments require supermajority (66%).

## Files

| File | Purpose |
|------|---------|
| `charter.yaml` | Constitution-style charter with approval voting |
| `members.yaml` | Five citizens across three districts |
| `run_example.py` | Runnable demo: 5 scenarios + chain verification |
| `README.md` | This file |

## Scenarios

1. **Education funding bill** — Approval voting with three options; winner determined by most approvals.
2. **Low turnout** — 1 of 5 citizens (20%) below 50% quorum; blocked.
3. **Tie blocks decision** — Rose vs tulip tie; must re-vote.
4. **Charter amendment** — Raise quorum via supermajority vote.
5. **Chain integrity** — `verify()` confirms all blocks.

## Run

```bash
cd /home/robin/OneDrive/University\ and\ such/My\ Papers/Works\ in\ progress/commonchain
uv run python examples/national_government/run_example.py
```

## Key takeaway

Approval voting plus quorum enforcement means legislation reflects broad
consent, not just a simple majority. The chain is the complete institutional
memory — every law, every vote, every amendment is hash-linked and
immutable.