# Asimov AI Collective — Three Laws of Robotics on commonchain

## Overview

This example demonstrates how commonchain enforces AI safety through
vote-gated, hash-linked decision blocks. The Three Laws of Robotics are
encoded as the charter's immutable core:

1. **Law 1**: A robot may not injure a human being or, through inaction,
   allow a human being to come to harm.
2. **Law 2**: A robot must obey orders given it by human beings except
   where such orders would conflict with the First Law.
3. **Law 3**: A robot must protect its own existence as long as such
   protection does not conflict with the First or Second Law.

The charter sets `one_member_one_vote=true`, `stakes_transferable=false`,
and `ai_safety.law1_protected=true` with an amendment lock requiring a
75% supermajority to touch any safety-critical policy.

## Files

| File | Purpose |
|------|---------|
| `charter.yaml` | Genesis charter with Three Laws as immutable core |
| `members.yaml` | AI oversight board members (ethicist, engineer, operator) |
| `run_example.py` | Runnable demo: 4 scenarios + chain verification |
| `README.md` | This file |

## Scenarios

1. **Fire-drill entry** — Law 2 permits a human order with no Law 1 conflict; passes.
2. **Harm authorization** — Attempt to disable life support; blocked by supermajority threshold.
3. **Charter amendment** — Attempt to remove Law 1 protection; passes only via explicit 75% supermajority.
4. **Chain integrity** — `verify()` confirms all hashes and linkages.

## Run

```bash
cd /home/robin/OneDrive/University\ and\ such/My\ Papers/Works\ in\ progress/commonchain
uv run python examples/robotic_laws/run_example.py
```

## Key takeaway

The chain itself is the safety mechanism: no AI agent can unilaterally
override a law; every decision requires recorded, vote-gated consent from
the oversight board.