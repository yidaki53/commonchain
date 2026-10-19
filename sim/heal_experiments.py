#!/usr/bin/env python3
"""
Self-healing experiments for commonchain's chain_coding layer.

Simulates block loss + helper failure across a matrix of configurations
and compares repair strategies on: recovery success rate, progress curve,
helpers needed for full recovery, bandwidth (shards transferred), and
storage overhead.

Run unsupervised:
    python /tmp/heal_experiments/heal_experiments.py

Outputs:
    /tmp/heal_experiments/results.json   -- full machine-readable report
    console summary                      -- human-readable comparison table
"""

from __future__ import annotations

import itertools
import json
import math
import random
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commonchain"))

from commonchain.chain import Collective
from commonchain.chain_coding import (
    CodecSession,
    RepairResult,
    decode_probe,
    repair_glitch,
)
from commonchain.chain_coding.codec_family import FOUNTAIN, LRC, REED_SOLOMON
from commonchain.governance import Ballot, DecisionBlock, Proposal, evaluate
from commonchain.models import Charter, Member

CODE_FAMILIES = [LRC, REED_SOLOMON, FOUNTAIN]
KN_RATIOS = [(2, 3), (3, 5), (4, 6), (4, 8)]
HELPER_MULTIPLIERS = [1.0, 1.0, 2.0]
FAILURE_PCTS = [0.0, 25.0, 50.0, 75.0]
SELECTIONS = ["all_available", "nearest_k", "random_k"]
N_BLOCKS = 12
SEED = 42


def make_collective(n_members: int = 5) -> tuple[Collective, list[Member]]:
    charter = Charter.model_validate(
        {
            "name": f"Exp Collective ({n_members} members)",
            "mission": "Experiment collective",
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
        title=f"Experiment block {block_index}",
        kind="ordinary",
        description=f"Synthetic block {block_index} for coding experiments",
    )
    ballots = [
        Ballot(voter=m.address, yes=True, choices=["yes"]) for m in members if m.active
    ]
    tally = evaluate(col.charter, members, proposal, ballots)
    block = col._append(tally)
    return block


def setup_codec(
    col: Collective,
    helpers: list[str],
    k: int,
    n: int,
    code_family: str,
    root: Path,
) -> CodecSession:
    session = CodecSession(
        chain=col,
        root=root,
        code_family=code_family,
        k=k,
        n=n,
        helpers={h: set() for h in helpers},
    )
    col.codec = session
    return session


@dataclass
class TrialResult:
    block_index: int
    code_family: str
    k: int
    n: int
    m_helpers: int
    failure_pct: float
    selection: str
    recovered: bool
    progress: float
    tokens_received: int
    helpers_available: int
    helpers_needed_for_full: int | None
    bandwidth_bytes: int
    progress_curve: list[tuple[int, float]]
    repair_time_s: float
    error: str = ""


@dataclass
class ExperimentConfig:
    code_family: str
    k: int
    n: int
    m_helpers: int
    failure_pct: float
    selection: str
    n_blocks: int
    seed: int


def _helper_shard_index(entries: list[dict], block_index: int, helper: str) -> int:
    for e in entries:
        if e.get("block_index") == block_index and e.get("helper") == helper:
            return e.get("shard_index", 999)
    return 999


def run_trial(
    config: ExperimentConfig,
    block_index: int,
    col: Collective,
    session: CodecSession,
    all_helpers: list[str],
    manifest_entries: list[dict],
    rng: random.Random,
) -> TrialResult:
    t0 = time.perf_counter()

    n_fail = int(round(config.failure_pct / 100.0 * len(all_helpers)))
    failed = set(rng.sample(all_helpers, n_fail)) if n_fail > 0 else set()
    available = [h for h in all_helpers if h not in failed]

    tokens: list[tuple[int, bytes]] = []
    for helper in available:
        for e in manifest_entries:
            if e.get("block_index") == block_index and e.get("helper") == helper:
                shard_index = e.get("shard_index", 0)
                shard_bytes = bytes.fromhex(e["shard"])
                tokens.append((shard_index, shard_bytes))
                break

    curve: list[tuple[int, float]] = []
    progressive_tokens: list[tuple[int, bytes]] = []
    helpers_needed_for_full: int | None = None
    for i, (shard_idx, tok) in enumerate(tokens, start=1):
        progressive_tokens.append((shard_idx, tok))
        report = decode_probe(block_index, config.k, config.n, config.code_family, progressive_tokens)
        curve.append((i, report.progress))
        if report.progress >= 1.0 and helpers_needed_for_full is None:
            helpers_needed_for_full = i

    try:
        result: RepairResult = repair_glitch(block_index, available, session)
        recovered = result.recovered
        progress = result.progress
        tokens_received = result.tokens_received
        error = result.error
    except Exception as exc:
        recovered = False
        progress = curve[-1][1] if curve else 0.0
        tokens_received = len(tokens)
        error = str(exc)

    body = col.chain[block_index].body_bytes()
    shard_size = max(1, math.ceil(len(body) / config.k))
    bandwidth_bytes = tokens_received * shard_size
    repair_time_s = time.perf_counter() - t0

    return TrialResult(
        block_index=block_index,
        code_family=config.code_family,
        k=config.k,
        n=config.n,
        m_helpers=config.m_helpers,
        failure_pct=config.failure_pct,
        selection=config.selection,
        recovered=recovered,
        progress=progress,
        tokens_received=tokens_received,
        helpers_available=len(available),
        helpers_needed_for_full=helpers_needed_for_full,
        bandwidth_bytes=bandwidth_bytes,
        progress_curve=curve,
        repair_time_s=repair_time_s,
        error=error,
    )


def run_experiment(config: ExperimentConfig) -> list[TrialResult]:
    rng = random.Random(config.seed)
    root = Path(
        f"/tmp/heal_experiments/run_{config.code_family}_k{config.k}_n{config.n}"
        f"_m{config.m_helpers}_f{config.failure_pct}_{config.selection}"
    )
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    n_members = max(config.m_helpers, config.k + 1)
    col, members = make_collective(n_members)
    all_helpers = [m.address for m in members]

    session = setup_codec(col, all_helpers, config.k, config.n, config.code_family, root)

    for i in range(config.n_blocks):
        decide_block(col, members, i)
        # decide_block -> col._append already calls session.record_block,
        # so the block is already in the manifest. Do not double-record.

    manifest_entries = list(session.manifest.entries) if session.manifest else []

    results: list[TrialResult] = []
    for block_index in range(config.n_blocks):
        result = run_trial(config, block_index, col, session, all_helpers, manifest_entries, rng)
        results.append(result)

    return results


def aggregate(results: list[TrialResult]) -> dict[str, Any]:
    if not results:
        return {}
    n = len(results)
    recovered = sum(1 for r in results if r.recovered)
    avg_progress = sum(r.progress for r in results) / n
    avg_tokens = sum(r.tokens_received for r in results) / n
    avg_helpers = sum(r.helpers_available for r in results) / n
    avg_bw = sum(r.bandwidth_bytes for r in results) / n
    avg_time = sum(r.repair_time_s for r in results) / n

    full_counts = [r.helpers_needed_for_full for r in results if r.helpers_needed_for_full is not None]
    avg_helpers_for_full = (sum(full_counts) / len(full_counts)) if full_counts else None

    curve_map: dict[int, list[float]] = {}
    for r in results:
        for h, p in r.progress_curve:
            curve_map.setdefault(h, []).append(p)
    avg_curve = [(h, sum(ps) / len(ps)) for h, ps in sorted(curve_map.items())]

    errors = [r.error for r in results if r.error]

    return {
        "n_trials": n,
        "recovered": recovered,
        "recovery_rate": recovered / n,
        "avg_progress": avg_progress,
        "avg_tokens_received": avg_tokens,
        "avg_helpers_available": avg_helpers,
        "avg_helpers_for_full_recovery": avg_helpers_for_full,
        "avg_bandwidth_bytes": avg_bw,
        "avg_repair_time_s": avg_time,
        "avg_progress_curve": avg_curve,
        "errors": errors[:5],
    }


def build_configs() -> list[ExperimentConfig]:
    configs: list[ExperimentConfig] = []
    for code_family, (k, n), failure_pct, selection in itertools.product(
        CODE_FAMILIES, KN_RATIOS, FAILURE_PCTS, SELECTIONS
    ):
        for mult in HELPER_MULTIPLIERS:
            m = max(n, math.ceil(mult * k))
            configs.append(
                ExperimentConfig(
                    code_family=code_family,
                    k=k,
                    n=n,
                    m_helpers=m,
                    failure_pct=failure_pct,
                    selection=selection,
                    n_blocks=N_BLOCKS,
                    seed=SEED,
                )
            )
    return configs


def print_summary(all_results: dict[str, list[TrialResult]]) -> None:
    print("\n" + "=" * 110)
    print("SELF-HEALING EXPERIMENT SUMMARY")
    print("=" * 110)
    print(
        f"{'Family':<14} {'k/n':<6} {'m':<4} {'Fail%':<7} {'Sel':<15} "
        f"{'RecRate':<9} {'AvgProg':<9} {'HlpsFull':<10} {'BW(B)':<10} {'Time(ms)':<9}"
    )
    print("-" * 110)

    rows = []
    for key, results in all_results.items():
        agg = aggregate(results)
        cfg = results[0]
        rows.append(
            (
                cfg.code_family,
                f"{cfg.k}/{cfg.n}",
                cfg.m_helpers,
                cfg.failure_pct,
                cfg.selection,
                agg["recovery_rate"],
                agg["avg_progress"],
                agg["avg_helpers_for_full_recovery"],
                agg["avg_bandwidth_bytes"],
                agg["avg_repair_time_s"] * 1000,
                key,
            )
        )

    rows.sort(key=lambda r: (-r[5], r[8]))

    for r in rows:
        print(
            f"{r[0]:<14} {r[1]:<6} {r[2]:<4} {r[3]:<7.0f} {r[4]:<15} "
            f"{r[5]:<9.3f} {r[6]:<9.3f} {str(r[7]):<10} {r[8]:<10.0f} {r[9]:<9.1f}"
        )

    print("-" * 110)
    print(f"Total configurations tested: {len(rows)}")
    print(f"Trials per configuration: {N_BLOCKS}")
    print(f"Total trials: {sum(len(v) for v in all_results.values())}")
    print()

    best = rows[0]
    print(f"BEST OVERALL: {best[0]} k/n={best[1]} m={best[2]} fail={best[3]}% sel={best[4]}")
    print(f"  recovery_rate={best[5]:.3f} avg_progress={best[6]:.3f} "
          f"helpers_for_full={best[7]} bandwidth={best[8]:.0f}B")


def write_json_report(all_results: dict[str, list[TrialResult]], path: Path) -> None:
    report: dict[str, Any] = {}
    for key, results in all_results.items():
        r0 = results[0]
        report[key] = {
            "config": {
                "code_family": r0.code_family,
                "k": r0.k,
                "n": r0.n,
                "m_helpers": r0.m_helpers,
                "failure_pct": r0.failure_pct,
                "selection": r0.selection,
                "n_blocks": N_BLOCKS,
                "seed": SEED,
            },
            "aggregate": aggregate(results),
            "trials": [
                {
                    "block_index": r.block_index,
                    "recovered": r.recovered,
                    "progress": r.progress,
                    "tokens_received": r.tokens_received,
                    "helpers_available": r.helpers_available,
                    "helpers_needed_for_full": r.helpers_needed_for_full,
                    "bandwidth_bytes": r.bandwidth_bytes,
                    "repair_time_s": r.repair_time_s,
                    "progress_curve": r.progress_curve,
                    "error": r.error,
                }
                for r in results
            ],
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to: {path}")


def main() -> None:
    configs = build_configs()
    print(f"Running {len(configs)} experiment configurations "
          f"({N_BLOCKS} blocks each) ...\n")

    all_results: dict[str, list[TrialResult]] = {}

    for idx, config in enumerate(configs, start=1):
        key = f"{config.code_family}_k{config.k}_n{config.n}_m{config.m_helpers}_f{config.failure_pct}_{config.selection}"
        print(f"[{idx}/{len(configs)}] {key}", end=" ... ", flush=True)
        results = run_experiment(config)
        all_results[key] = results
        agg = aggregate(results)
        print(f"recovery_rate={agg['recovery_rate']:.3f} "
              f"avg_progress={agg['avg_progress']:.3f}")

    print_summary(all_results)
    write_json_report(all_results, Path("/tmp/heal_experiments/results.json"))


if __name__ == "__main__":
    main()
