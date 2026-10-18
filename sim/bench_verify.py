"""Night 5, Job 4: verification scaling benchmark.

``stress.py`` times verify() at exactly one chain length (50k). That supports
"it works" but not the scaling claims the paper makes: verify() must grow
linearly with chain height (it rehashes every block) while verify_block()
stays O(1) in neighbourhood size regardless of height. One timing point cannot
show a slope; this benchmark produces the citable curve.

Per chain length L in ``LENGTHS``:
  build a chain of L real blocks (propose, 5 of 9 members voting),
  then time:
    verify_full_s        full-chain verify()          (expect O(L))
    verify_block_us      mean verify_block() over a    (expect O(1))
                         random sample of indices
    blocks_per_s         append throughput at length L

``--smoke`` shrinks the lengths so the job finishes in seconds. Output:
results/night5/verify_bench.csv (+ isolated *_smoke file).
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective  # noqa: E402
from commonchain.governance import Ballot  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

RESULTS = ROOT / "results" / "night5"
FIELDS = [
    "chain_length", "verify_full_s", "verify_full_us_per_block",
    "verify_block_us", "append_blocks_per_s", "elapsed_s",
]
SAMPLES = 200  # verify_block timings per length


def bench_length(n_blocks: int) -> dict:
    charter = Charter.model_validate(
        {"name": "bench", "mission": "verification scaling", "quorum_pct": 50.0}
    )
    members = [Member(address=f"0x{i:04x}") for i in range(9)]
    col = Collective.from_charter(charter, members)
    addrs = [m.address for m in members]
    voters = addrs[:5]

    t0 = time.time()
    for i in range(n_blocks):
        col.propose(f"b{i}", [Ballot(voter=a, yes=(i % 2 == 0))
                              for a in voters])
    t_append = time.time() - t0

    t0 = time.time()
    ok = col.verify()
    t_verify = time.time() - t0
    assert ok, "chain failed to verify during benchmark"

    rng = random.Random(42)
    t0 = time.time()
    for _ in range(SAMPLES):
        col.verify_block(rng.randrange(len(col.chain)))
    t_block = (time.time() - t0) / SAMPLES

    return {
        "chain_length": n_blocks,
        "verify_full_s": round(t_verify, 4),
        "verify_full_us_per_block": round(t_verify / n_blocks * 1e6, 3),
        "verify_block_us": round(t_block * 1e6, 3),
        "append_blocks_per_s": round(n_blocks / t_append, 1),
        "elapsed_s": round(time.time() - t0 + t_append, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    suffix = "_smoke" if args.smoke else ""
    out = RESULTS / f"verify_bench{suffix}.csv"
    lengths = [100, 500] if args.smoke else [1000, 5000, 10000, 25000]

    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for L in lengths:
            row = bench_length(L)
            w.writerow(row)
            f.flush()
            print(f"[bench] L={L}: verify={row['verify_full_s']}s "
                  f"({row['verify_full_us_per_block']}us/block), "
                  f"verify_block={row['verify_block_us']}us", flush=True)
    print(f"[bench] complete -> {out}", flush=True)


if __name__ == "__main__":
    main()
