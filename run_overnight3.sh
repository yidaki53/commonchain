#!/usr/bin/env bash
# Night run 3: domain-neutral core + voting rules. Unsupervised by design.
#
# Isolation: every job writes under results/night3/ with its OWN state file.
# A --smoke preflight can never truncate a full grid (night-1 lesson).
set -u
cd "$(dirname "$0")"

RESULTS=results/night3
mkdir -p "$RESULTS" logs

run() {
  echo "=== $1 ==="
  shift
  if uv run "$@" 2>&1; then
    echo "--- OK: $1"
  else
    echo "--- FAILED (night continues): $1"
  fi
}

# Job 0: quick smoke of every new job against ISOLATED smoke state files.
run "Job 0a: voting smoke"       python sim/sweep_voting.py --smoke
run "Job 0b: template fuzz smoke" python sim/template_fuzz.py
run "Job 0c: ballot fuzz smoke"  python sim/ballot_fuzz.py
run "Job 0d: stress smoke"       python sim/stress.py --blocks 20000 --fuzz 50 --amend 200

# Job 1: full voting-rule sweep (3 rules x 4 N x 4 apathy x 20 seeds = 960).
run "Job 1: voting-rule sweep"   python sim/sweep_voting.py --seeds 20

# Job 2: template fuzz at depth (every kind x 100 random decisions).
run "Job 2: template fuzz"       python sim/template_fuzz.py

# Job 3: ballot / choice fuzz + hash round-trip determinism + tamper.
run "Job 3: ballot fuzz"         python sim/ballot_fuzz.py

# Job 4: scale stress -- 500k blocks (10x night 1), tamper fuzz, core hammer.
# Fuzz is O(1) per iteration since verify_block(); 500 iterations is seconds.
run "Job 4: scale stress"        python sim/stress.py --blocks 500000 --fuzz 500 --amend 2000

# Job 5: analysis + gate.
run "Job 5: confidence intervals" python analysis/confidence.py
run "Job 5: figures"              python analysis/make_figures.py
run "Job 5: test gate"            python -m pytest tests/ -q -p no:cacheprovider
run "Job 5: lint gate"            ruff check commonchain sim analysis tests

echo "=== SUMMARY ==="
uv run python - <<'EOF'
import csv
from pathlib import Path
p = Path("results/night3/voting_sweep.csv")
rows = list(csv.DictReader(p.open())) if p.exists() else []
print(f"voting cells: {len(rows)}")
bad = [r for r in rows if r.get("pass_rate") in (None, "", "-1")]
print(f"failed cells: {len(bad)}")
for rule in ("binary", "plurality", "approval"):
    rs = [float(r["pass_rate"]) for r in rows if r["voting_rule"] == rule and r.get("pass_rate") not in (None, "", "-1")]
    print(f"{rule}: n={len(rs)} mean_pass={sum(rs)/len(rs):.3f}" if rs else f"{rule}: no data")
EOF
echo "=== NIGHT RUN 3 COMPLETE $(date -u +%FT%TZ) ==="
