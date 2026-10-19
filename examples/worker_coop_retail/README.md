# Red Rose Worker Co-op Retail — Worker-Owned Chain on commonchain

## Overview

This example demonstrates how commonchain powers a worker-owned cooperative
retail chain:

* Worker-owners are members — one worker, one vote.
* `stakes_transferable: false` — memberships are soulbound, never sold or transferred.
* `payroll` module with `equal` policy and `stable_base_share: 0.5`.
* `profit_sharing` module distributing 80% of profits to workers quarterly.
* `voting_rule: binary` for yes/no business decisions.

## Files

| File | Purpose |
|------|---------|
| `charter.yaml` | Co-op charter with equal payroll and profit sharing |
| `members.yaml` | Four worker-owners across two stores |
| `run_example.py` | Runnable demo: 6 scenarios + chain verification |
| `README.md` | This file |

## Scenarios

1. **Extend store hours** — Binary yes/no vote passes (75% >= 50%).
2. **Soulbound stake transfer** — Attempt to make stakes transferable; rejected at charter validation.
3. **Non-worker voting** — Customer attempts to vote; rejected as non-member.
4. **Profit distribution** — Unanimous worker-owner approval for Q3 profit split.
5. **Worker offboarding** — Departing worker's stake is burned, not transferred; deactivated members cannot vote.
6. **Chain integrity** — `verify()` confirms all blocks.

## Run

```bash
cd /home/robin/OneDrive/University\ and\ such/My\ Papers/Works\ in\ progress/commonchain
uv run python examples/worker_coop_retail/run_example.py
```

## Key takeaway

The co-op is owned and governed by its workers. No manager class is needed:
every decision — hours, pricing, sourcing, profit distribution — is
vote-gated and recorded immutably on-chain.