# WARP.md — commonchain

**Every AI agent working in this repo MUST read this file first.**

## What this is

FOSS self-governance core for worker-owned collectives: charter = genesis
block, decisions = hash-linked vote-gated blocks, one-worker-one-vote,
soulbound stakes, pluggable payroll/delegation/mandate modules. Roadmap:
`docs/plan_*.md`; current architecture: `docs/`.

## Python environment — uv ONLY

This repo uses **uv for every Python command**. No bare `python`, `python3`,
`pytest`, or `poetry` invocations — always go through `uv run` from the repo
root:

```bash
uv sync                                            # creates .venv + uv.lock (already done)
uv run python -m pytest tests/ -q --cov=commonchain --cov-report=term
uv run ruff check commonchain sim analysis tests
uv run python analysis/make_figures.py
uv run python sim/sweep.py --job gov --cells 4 --seeds 2
uv run commonchain --help                          # CLI (entry point: commonchain.cli:main)
```

The package is installed editable into `.venv` by `uv sync`; `PYTHONPATH` is
NOT needed. Shell scripts (`run_overnight.sh`, `run_overnight2.sh`) already
use `uv run` — keep it that way.

Pitfall: a stale `VIRTUAL_ENV` env var (e.g. from activating another repo's
venv) makes uv print a warning and ignore that env — harmless, but do not add
`--active` to "fix" it.

## Hard rules

- NEVER commit or push, even with `--no-verify`. The human handles git.
- No emojis anywhere in code, docs, comments or results.
- `results/` data artifacts are immutable once written; new runs go to
  `results/night<N>/` with their OWN checkpoint state file. Sharing
  `sweep_state.json` between a smoke test (`--cells`) and a full grid run
  truncates CSVs — this destroyed `gov_sweep.csv` once (recovered from backup).
- Analysis code must not silently depend on column names: aggregation scripts
  broke twice on renames (`mandate_concentration`→`hhi_concentration`,
  `floor_violation`→`floor_violation_rate`). When renaming a metric, grep
  `sim/ analysis/` for the old name.
- `floor_violation_rate` is non-discriminating (always 0) — do not build new
  tables on it; replace with a meaningful metric.
- OneDrive is a FUSE mount with eventual consistency: verify edits with a
  fresh read; do not rely on shell state persisting between commands.

## Layout

```
commonchain/   the package (models, chain, governance, modules, cli, templates)
contracts/     Solidity mirrors (Solidity 0.8.x, OpenZeppelin v5, Foundry-style)
sim/           parameter sweeps + stress/fuzz (checkpoint to results/*_state.json)
analysis/      CI aggregation, tables, figures
results/       immutable outputs + OVERNIGHT_FINDINGS.md
tests/         invariant-first test suite (gate: pytest + ruff, both via uv)
docs/          architecture, playbook (chartering, jurisdictions, dissolution)
```

## Testing gate (must be green before reporting done)

`uv run python -m pytest tests/ -q` (124 tests, all green) and
`uv run ruff check commonchain sim analysis tests` (clean).

The nightly unsupervised suite is `uv run python nightly_runner.py`: it runs
the full pytest suite plus the three example scenarios end-to-end
(`examples/{robotic_laws,national_government,worker_coop_retail}/run_example.py`)
and exits non-zero on any stage failure. The adversarial edge-case tests
live in `tests/test_examples_adversarial.py` (25 tests: Three Laws amendment
attacks, Byzantine/double/non-member voting, quorum and tie handling,
soulbound stake transfer, double-spend, chain tampering, empty proposals,
RS/Fountain/LRC codec edge cases, all-helpers-offline).

## Codec Performance Optimizations (self-healing section)

The codec layer (`commonchain/chain_coding/{gf256,lrc,fountain}.py`) was
optimized in four tiers. Repair latency is already <1ms for all LRC configs;
these optimizations matter at scale (MB+ blocks, high throughput).

### Tier 1 — Pythonic quick wins (done, <1 hr, 2-5x)
* `gf256.rs_encode_shards`: precompute `xj^i` powers once per evaluation point
  instead of inside the per-byte loop (~30% savings on the O(n x length x k)
  GF-mul hot path).
* `lrc.lrc_encode_shards` / `lrc.lrc_decode_from_available`: replace byte-by-byte
  XOR loops with `int.from_bytes` / `int.to_bytes` integer XOR for blocks
  >= 64 bytes (~5-10x).
* `fountain.fountain_encode_shards` / `fountain.fountain_decode_from_available`:
  same `int.from_bytes` XOR for blocks >= 64 bytes (~5-10x).

### Tier 2 — NumPy vectorization (done, existing dep, 10-50x)
* `gf256`: lazy 256x256 GF(2^8) multiplication table (`_GF_MUL_TABLE` as uint8)
  with `gf_mul_vec`/`gf_mul_mat_vec` vectorized accessors.
* `gf256._rs_encode_shards_numpy`: stacks shards into a `(k, length)` array and
  applies row operations to all byte positions simultaneously.
* `gf256._rs_decode_from_available_numpy`: vectorized Gauss-Jordan decode for
  blocks >= 4 KiB — inverts the (k x k) Vandermonde matrix once, then applies
  it to the stacked evaluation tensor with the GF table.
* `lrc.lrc_encode_shards`: `np.bitwise_xor.reduce` for local parity on large blocks.

### Tier 4 — Conditional CUDA (done, blocks >= 16 KiB only)
* `gf256.CUDA_THRESHOLD = 16384`: large blocks dispatch to CuPy GPU path with
  on-device GF table; smaller blocks stay pure-Python to avoid host<->device
  transfer overhead. CuPy is an optional import with NumPy fallback — no new
  hard dependency.

### Deferred
* Cython Tier 3 (build complexity not justified for current throughput).

### Pitfalls (learned the hard way)
* `fountain`: the encoder derives each shard's degree and source set with
  `Random(seed + j)` per shard index j — the peeling decoder replays exactly
  this. If you change one side's RNG scheme, decode silently returns garbage
  (peeling "succeeds" on wrong source sets) instead of failing loudly. Always
  keep encode/decode replay in lockstep.
* `payroll` parameter validation happens at payout time
  (`payroll.require_enabled`, raises `PayrollError`), NOT at
  `Charter.model_validate` — `Charter.modules` is a free-form dict. Test
  validation through `payroll.distribute`, not charter construction.
* `supermajority_pct` is the threshold for `kind="charter_amendment"`
  proposals (`evaluate` selects it from the charter); a 2/3 vote passes a
  66% threshold but fails a 75% one — set the fixture threshold to match
  the intent of each test.

## Citation

Any external data, method or figure reuse: cite it (see `README.md`
Citation section and `docs/playbook/`).
