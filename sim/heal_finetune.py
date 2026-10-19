#!/usr/bin/env python3
"""LRC finetuning experiments for commonchain's self-healing layer.

Sweeps LRC-specific parameters (group size, k/n ratio, global parity)
on top of the production-default code family (LRC) to find the best
configuration for each failure regime.

Run:
    python sim/heal_finetune.py          # full grid
    python sim/heal_finetune.py --smoke   # quick sanity check
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective  # noqa: E402
from commonchain.chain_coding.codec_family import LRC  # noqa: E402
from commonchain.chain_coding.lrc import (  # noqa: E402
    _layout,
    lrc_decode_from_available,
    lrc_encode_shards,
)
from commonchain.governance import Ballot, DecisionBlock, Proposal, evaluate  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

CODE_FAMILY = LRC
KN_RATIOS = [(2, 3), (3, 5), (4, 8)]
GROUP_SIZES = [2, 3, 4]
FAILURE_PCTS = [0.0, 25.0, 50.0, 75.0]
HELPER_MODES = ["k", "n"]
N_BLOCKS = 12
SEED = 42
SMOKE_N_BLOCKS = 4
SMOKE_SEEDS = 2


def valid_group_sizes(k: int) -> list[int]:
    sizes = []
    for g in GROUP_SIZES:
        if g > k:
            continue
        sizes.append(g)
    return sizes or [2]


def make_collective(n_members: int = 5) -> tuple[Collective, list[Member]]:
    charter = Charter.model_validate(
        {
            "name": f"Finetune Collective ({n_members} members)",
            "mission": "LRC finetune collective",
            "kind": "coop",
            "quorum_pct": 60.0,
            "pass_pct": 50.0,
            "supermajority_pct": 66.0,
            "voting_rule": "binary",
            "modules": {},
        }
    )
    members = [
        Member(address=f"0x{i:03x}", display_name=f"Member {i}", active=True)
        for i in range(n_members)
    ]
    col = Collective.from_charter(charter, members)
    return col, members


def decide_block(col: Collective, members: list[Member], block_index: int) -> DecisionBlock:
    proposal = Proposal(
        title=f"Finetune block {block_index}",
        kind="ordinary",
        description=f"Synthetic block {block_index} for LRC finetuning",
    )
    ballots = [
        Ballot(voter=m.address, yes=True, choices=["yes"]) for m in members if m.active
    ]
    tally = evaluate(col.charter, members, proposal, ballots)
    block = col._append(tally)
    return block


def encode_block_lrc(block: DecisionBlock, k: int, n: int, group_size: int) -> list[bytes]:
    body = block.body_bytes()
    shard_len = (len(body) + k - 1) // k
    data_shards = [body[i * shard_len:(i + 1) * shard_len] for i in range(k)]
    if len(data_shards[-1]) < shard_len:
        data_shards[-1] = data_shards[-1] + b"\x00" * (shard_len - len(data_shards[-1]))
    return lrc_encode_shards(data_shards, n, k, group_size=group_size)


def simulate_repair(
    shards: list[bytes],
    k: int,
    n: int,
    group_size: int,
    failure_pct: float,
    m_helpers: int,
    rng: random.Random,
) -> tuple[bool, float, int, float, float]:
    n_fail = int(round(n * failure_pct / 100.0))
    all_indices = list(range(n))
    failed = set(rng.sample(all_indices, n_fail)) if n_fail > 0 else set()
    available_indices = [i for i in all_indices if i not in failed]

    if m_helpers == "k":
        m = k
    else:
        m = n

    if len(available_indices) <= m:
        queried = available_indices
    else:
        queried = rng.sample(available_indices, m)

    available = {i: shards[i] for i in queried}

    t0 = time.time()
    recovered, progress = lrc_decode_from_available(available, k, n, group_size=group_size)
    repair_time = time.time() - t0

    recovered_full = progress >= 1.0
    bandwidth = sum(len(shards[i]) for i in queried)

    return recovered_full, progress, len(queried), bandwidth, repair_time


@dataclass
class TrialResult:
    k: int
    n: int
    group_size: int
    failure_pct: float
    m_mode: str
    block_index: int
    recovered: bool
    progress: float
    helpers_available: int
    bandwidth_bytes: int
    repair_time_s: float


def run_experiment(k: int, n: int, group_size: int, failure_pct: float,
                   m_mode: str, n_blocks: int, seed: int) -> list[TrialResult]:
    rng = random.Random(seed)
    results: list[TrialResult] = []

    for bi in range(n_blocks):
        body = bytes(rng.randrange(256) for _ in range(rng.randrange(64, 256)))
        shard_len = (len(body) + k - 1) // k
        data_shards = [body[i * shard_len:(i + 1) * shard_len] for i in range(k)]
        if len(data_shards[-1]) < shard_len:
            data_shards[-1] = data_shards[-1] + b"\x00" * (shard_len - len(data_shards[-1]))

        shards = lrc_encode_shards(data_shards, n, k, group_size=group_size)

        recovered, progress, helpers, bandwidth, repair_time = simulate_repair(
            shards, k, n, group_size, failure_pct, m_mode, rng
        )

        results.append(TrialResult(
            k=k, n=n, group_size=group_size,
            failure_pct=failure_pct, m_mode=m_mode,
            block_index=bi,
            recovered=recovered,
            progress=progress,
            helpers_available=helpers,
            bandwidth_bytes=bandwidth,
            repair_time_s=repair_time,
        ))

    return results


def aggregate(results: list[TrialResult]) -> dict[str, Any]:
    if not results:
        return {}
    n = len(results)
    recovery_rate = sum(1 for r in results if r.recovered) / n
    avg_progress = sum(r.progress for r in results) / n
    avg_bw = sum(r.bandwidth_bytes for r in results) / n
    avg_time = sum(r.repair_time_s for r in results) / n
    full_recovery_helpers = [
        r.helpers_available for r in results if r.recovered
    ]
    avg_helpers_full = (sum(full_recovery_helpers) / len(full_recovery_helpers)
                        if full_recovery_helpers else None)
    return {
        "recovery_rate": round(recovery_rate, 4),
        "avg_progress": round(avg_progress, 4),
        "avg_helpers_for_full_recovery": round(avg_helpers_full, 2) if avg_helpers_full else None,
        "avg_bandwidth_bytes": round(avg_bw, 0),
        "avg_repair_time_s": round(avg_time, 4),
        "n_trials": n,
    }


def build_configs(smoke: bool = False) -> list[dict]:
    configs = []
    n_blocks = SMOKE_N_BLOCKS if smoke else N_BLOCKS
    n_seeds = SMOKE_SEEDS if smoke else 30

    for k, n in KN_RATIOS:
        for gs in valid_group_sizes(k):
            groups, lpc = _layout(k, n, group_size=gs)
            gpc = n - k - lpc
            if gpc < 0:
                continue
            for fail in FAILURE_PCTS:
                for m_mode in HELPER_MODES:
                    for s in range(n_seeds):
                        configs.append({
                            "k": k, "n": n, "group_size": gs,
                            "failure_pct": fail, "m_mode": m_mode,
                            "seed": s, "n_blocks": n_blocks,
                        })
    return configs


def main() -> None:
    smoke = "--smoke" in sys.argv
    configs = build_configs(smoke=smoke)
    print(f"Running {len(configs)} LRC finetune configurations "
          f"({SMOKE_N_BLOCKS if smoke else N_BLOCKS} blocks each) ...\n")

    all_results: dict[str, list[TrialResult]] = {}

    for idx, cfg in enumerate(configs, start=1):
        key = (f"lrc_k{cfg['k']}_n{cfg['n']}_gs{cfg['group_size']}"
               f"_f{cfg['failure_pct']}_m{cfg['m_mode']}_s{cfg['seed']}")
        print(f"[{idx}/{len(configs)}] {key}", end=" ... ", flush=True)

        trial_results = run_experiment(
            k=cfg["k"], n=cfg["n"], group_size=cfg["group_size"],
            failure_pct=cfg["failure_pct"], m_mode=cfg["m_mode"],
            n_blocks=cfg["n_blocks"], seed=cfg["seed"],
        )
        all_results[key] = trial_results
        agg = aggregate(trial_results)
        print(f"recovery={agg['recovery_rate']:.3f} "
              f"progress={agg['avg_progress']:.3f} "
              f"helpers={agg['avg_helpers_for_full_recovery']} "
              f"bw={agg['avg_bandwidth_bytes']:.0f}B")

    print("\n" + "=" * 100)
    print("LRC FINETUNE SUMMARY (aggregated over seeds)")
    print("=" * 100)

    grouped: dict[tuple, list[TrialResult]] = defaultdict(list)
    for key, results in all_results.items():
        r0 = results[0]
        gkey = (r0.k, r0.n, r0.group_size, r0.failure_pct, r0.m_mode)
        grouped[gkey].extend(results)

    rows = []
    for gkey, results in sorted(grouped.items()):
        k, n, gs, fail, m_mode = gkey
        agg = aggregate(results)
        rows.append((k, n, gs, fail, m_mode, agg))

    header = f"{'k':<3} {'n':<3} {'gs':<3} {'fail%':<6} {'m':<4} {'rec':<7} {'prog':<7} {'helpers':<9} {'bw(B)':<8} {'time(ms)':<9}"
    print(header)
    print("-" * len(header))
    for k, n, gs, fail, m_mode, agg in rows:
        t = agg['avg_repair_time_s'] * 1000
        print(f"{k:<3} {n:<3} {gs:<3} {fail:<6.0f} {m_mode:<4} "
              f"{agg['recovery_rate']:<7.3f} {agg['avg_progress']:<7.3f} "
              f"{str(agg['avg_helpers_for_full_recovery']):<9} {agg['avg_bandwidth_bytes']:<8.0f} {t:<9.1f}")

    print("\n" + "=" * 100)
    print("BEST LRC CONFIG PER FAILURE REGIME (max recovery, then min bandwidth)")
    print("=" * 100)
    for fail in FAILURE_PCTS:
        candidates = [r for r in rows if r[3] == fail]
        if not candidates:
            continue
        best = max(candidates, key=lambda r: (r[5]['recovery_rate'], -r[5]['avg_bandwidth_bytes']))
        k, n, gs, _, m_mode, agg = best
        print(f"  fail={fail:4.0f}%: k={k} n={n} gs={gs} m={m_mode} "
              f"rec={agg['recovery_rate']:.3f} bw={agg['avg_bandwidth_bytes']:.0f}B "
              f"time={agg['avg_repair_time_s']*1000:.1f}ms")

    report: dict[str, Any] = {}
    for key, results in all_results.items():
        r0 = results[0]
        report[key] = {
            "config": {
                "code_family": "lrc",
                "k": r0.k,
                "n": r0.n,
                "group_size": r0.group_size,
                "failure_pct": r0.failure_pct,
                "m_mode": r0.m_mode,
                "n_blocks": N_BLOCKS,
                "seed": SEED,
            },
            "aggregate": aggregate(results),
            "trials": [asdict(r) for r in results],
        }

    out_dir = ROOT / "results" / "heal_experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "finetune_results.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to: {out_path}")


if __name__ == "__main__":
    main()
