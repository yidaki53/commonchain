#!/usr/bin/env bash
# Night run 2: statistical rigor + delegation experiment.
#
# Writes to results/night2/ with its OWN state file, so a --cells smoke test can
# never truncate a full grid. Night 1 lost gov_sweep.csv this way: the smoke test
# and the full run shared sweep_state.json, the state file claimed every cell was
# done, and the live CSV kept only the tail. Isolated sandbox prevents a repeat.
set -u
cd "$(dirname "$0")"

RESULTS=results/night2
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

# Job 1: cluster-bootstrap CIs over the night-1 CSVs (no re-simulation).
run "Job 1: confidence intervals" python3 analysis/confidence.py

# Job 2: pass_pct sweep -- the job that may overturn the pass_pct=50 default.
run "Job 2: pass threshold sweep" python3 sim/sweep_pass.py --seeds 20

# Job 3: mandate incumbency -- makes the HHI-vs-term question answerable.
run "Job 3: mandate incumbency" python3 sim/sweep_mandate.py --seeds 50

# Job 4: liquid delegation -- turnout gain vs power concentration.
run "Job 4: delegation sweep" python3 sim/sweep_delegation.py --seeds 20

# Job 5: gate -- tests, lint, figures. Must be last.
run "Job 5: test gate" python3 -m pytest -q -p no:cacheprovider
run "Job 5: lint gate" ruff check .
run "Job 5: figures" python3 analysis/make_figures.py

echo "=== NIGHT RUN 2 COMPLETE ==="
