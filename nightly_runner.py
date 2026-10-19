#!/usr/bin/env python3
"""Nightly unsupervised test suite for commonchain.

Runs, in order:

1. The full pytest suite (unit + adversarial example tests).
2. The three example scenarios (AI safety, national government, worker
   co-op) end-to-end via their run_example.py scripts.

Exit code is non-zero if any stage fails, so a cron/CI wrapper can alert.
Usage:

    python nightly_runner.py [--skip-examples] [--skip-tests]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EXAMPLES = [
    ROOT / "examples" / "robotic_laws" / "run_example.py",
    ROOT / "examples" / "national_government" / "run_example.py",
    ROOT / "examples" / "worker_coop_retail" / "run_example.py",
]


def run_stage(name: str, cmd: list[str], cwd: Path) -> bool:
    print(f"\n=== NIGHTLY STAGE: {name} ===", flush=True)
    print(" ".join(cmd), flush=True)
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(cwd))
    elapsed = time.monotonic() - started
    ok = proc.returncode == 0
    status = "OK" if ok else f"FAILED (exit {proc.returncode})"
    print(f"=== {name}: {status} in {elapsed:.1f}s ===", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true",
                        help="skip the pytest stage")
    parser.add_argument("--skip-examples", action="store_true",
                        help="skip the example scenarios stage")
    args = parser.parse_args()

    py = sys.executable
    failures: list[str] = []

    if not args.skip_tests:
        ok = run_stage(
            "pytest",
            [py, "-m", "pytest", "tests/", "-q", "--tb=short"],
            ROOT,
        )
        if not ok:
            failures.append("pytest")

    if not args.skip_examples:
        for example in EXAMPLES:
            if not example.exists():
                print(f"MISSING example script: {example}", flush=True)
                failures.append(str(example))
                continue
            ok = run_stage(example.parent.name, [py, str(example)], ROOT)
            if not ok:
                failures.append(example.parent.name)

    print("\n=== NIGHTLY SUMMARY ===", flush=True)
    if failures:
        print(f"FAILED stages: {', '.join(failures)}", flush=True)
        return 1
    print("all stages passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
