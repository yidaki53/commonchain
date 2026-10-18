#!/usr/bin/env bash
# Night run 5: constitutional capture & fragmented preferences. Unsupervised.
#
# Four experiments, each closing a gap the earlier nights flagged but never
# measured (or measured without intervals):
#   Job 1  fragmented-preference voting: night 3's minority-win was ~0 by
#          construction (uniform-random favorites = no coherent minority).
#          Bloc structure makes minority winners real and contrasts rules.
#   Job 2  constitutional capture: stress.py only proved the IMMUTABLE core
#          is unamendable. This measures the amendable policy layer: can a
#          disciplined bloc legally lower the supermajority (cascade), and
#          does an engaged honest majority recover? Phase diagram in
#          bloc size x turnout x supermajority.
#   Job 3  preference-aligned vs random delegation: night 2's build_delegation_
#          map chose delegates uniformly at random; real liquid democracy lets
#          you choose. Does alignment buy the turnout gain without the
#          representation distortion?
#   Job 4  verification scaling curve (O(n) verify vs O(1) verify_block) as a
#          citable figure instead of stress.py's single timing point.
#   Job 5  CI upgrade: night-2's mandate/delegation tables were point
#          estimates (CI machinery existed but wasn't wired to them).
#
# Isolation: every job writes under results/night5/ with its OWN state file.
# A --smoke preflight can never truncate a full grid (night-1 lesson).
set -u
cd "$(dirname "$0")"

RESULTS=results/night5
mkdir -p "$RESULTS" logs 2>/dev/null || true
mkdir -p "$RESULTS"

run() {
  desc="$1"
  echo "=== $1 ==="
  shift
  if uv run "$@" 2>&1; then
    echo "--- OK: $desc"
  else
    echo "--- FAILED (night continues): $desc"
  fi
}

# ---- Job 0: smoke preflight (isolated smoke state files) ----
run "Job 0a: fragmentation smoke"  python sim/sweep_fragmentation.py --smoke
run "Job 0b: amendment smoke"      python sim/sweep_amendment.py --smoke
run "Job 0c: deleg-blocs smoke"    python sim/sweep_deleg_blocs.py --smoke
run "Job 0d: verify bench smoke"   python sim/bench_verify.py --smoke
run "Job 0e: preflight env"        python -c "import sys, pydantic, matplotlib; print(sys.version); print('pydantic', pydantic.VERSION); print('matplotlib', matplotlib.__version__)"

# ---- Job 1: fragmented-preference voting sweep (full grid) ----
run "Job 1: fragmentation sweep"   python sim/sweep_fragmentation.py --seeds 30

# ---- Job 2: constitutional capture sweep ----
run "Job 2: capture sweep"         python sim/sweep_amendment.py --seeds 30

# ---- Job 3: aligned-delegation sweep ----
run "Job 3: deleg-blocs sweep"     python sim/sweep_deleg_blocs.py --seeds 30

# ---- Job 4: verification scaling benchmark ----
run "Job 4: verify bench"          python sim/bench_verify.py

# ---- Job 5: CI tables (night-5 data + night-2 upgrades) ----
run "Job 5: CI tables"             python analysis/tables_night5.py

# ---- Job 6: figures ----
run "Job 6: figures"               python analysis/figures_night5.py

# ---- Job 7: ML experiment layer (night-5 mlruns dir, dependency-light) ----
run "Job 7: mlflow-lite log"       env COMMONCHAIN_MLRUNS=results/night5/mlruns python - <<'EOF'
import csv, sys
from pathlib import Path
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from analysis.ml_logger import start_run, log_params, log_metrics, log_artifact, end_run

def rows(name):
    p = ROOT / "results/night5" / name
    return list(csv.DictReader(p.open())) if p.exists() else []

frag = rows("fragmentation_sweep.csv")
if frag:
    run = start_run("fragmentation-night5")
    run.log_params({"n_cells": len(frag), "sweep": "fragmentation"})
    for rule in sorted({r["voting_rule"] for r in frag}):
        sub = [r for r in frag if r["voting_rule"] == rule
               and r["pass_rate"] not in ("", "-1")]
        if not sub: continue
        n = len(sub)
        run.log_metrics({
            f"{rule}/minority_win": sum(float(r["minority_win_rate"]) for r in sub)/n,
            f"{rule}/tie_rate": sum(float(r["tie_rate"]) for r in sub)/n,
            f"{rule}/pass_rate": sum(float(r["pass_rate"]) for r in sub)/n,
        })
    run.log_artifact(str(ROOT / "results/night5/fragmentation_sweep.csv"))
    end_run()

cap = rows("amendment_sweep.csv")
if cap:
    run = start_run("capture-night5")
    run.log_params({"n_cells": len(cap), "sweep": "amendment_capture"})
    good = [r for r in cap if r["captured_any"] not in ("", "-1")]
    if good:
        n = len(good)
        run.log_metrics({
            "capture_rate": sum(float(r["captured_any"]) for r in good)/n,
            "chain_ok_frac": sum(float(r["chain_ok"]) for r in good)/n,
        })
    run.log_artifact(str(ROOT / "results/night5/amendment_sweep.csv"))
    end_run()

deb = rows("deleg_blocs_sweep.csv")
if deb:
    run = start_run("deleg-blocs-night5")
    run.log_params({"n_cells": len(deb), "sweep": "deleg_blocs"})
    for al in sorted({r["aligned_frac"] for r in deb}):
        sub = [r for r in deb if r["aligned_frac"] == al
               and r["deleg_pass"] not in ("", "-1")]
        if not sub: continue
        n = len(sub)
        run.log_metrics({
            f"aligned_{al}/delta_pass": sum(
                float(r["deleg_pass"]) - float(r["baseline_pass"])
                for r in sub)/n,
            f"aligned_{al}/fidelity": sum(float(r["fidelity"]) for r in sub)/n,
        })
    run.log_artifact(str(ROOT / "results/night5/deleg_blocs_sweep.csv"))
    end_run()
print("[mlflow-lite] night-5 runs logged")
EOF

# ---- Job 8: gate (tests + lint) ----
run "Job 8a: test gate"            python -m pytest tests/ -q -p no:cacheprovider
run "Job 8b: lint gate"            ruff check commonchain sim analysis tests || true

# ---- Job 9: summary ----
echo "=== SUMMARY ==="
uv run python - <<'EOF'
import csv
from pathlib import Path

def load(name):
    p = Path("results/night5") / name
    return list(csv.DictReader(p.open())) if p.exists() else []

frag = [r for r in load("fragmentation_sweep.csv") if r["pass_rate"] not in ("", "-1")]
print(f"fragmentation cells: {len(frag)}")
for rule in ("binary", "plurality", "approval"):
    sub = [r for r in frag if r["voting_rule"] == rule]
    if not sub: continue
    n = len(sub)
    mw = sum(float(r["minority_win_rate"]) for r in sub)/n
    tie = sum(float(r["tie_rate"]) for r in sub)/n
    sat = sum(float(r["mean_satisfaction"]) for r in sub)/n
    print(f"  {rule}: minority_win={mw:.3f} tie={tie:.3f} satisfaction={sat:.3f}")

cap = [r for r in load("amendment_sweep.csv") if r["captured_any"] not in ("", "-1")]
ok = sum(1 for r in cap if r["chain_ok"] == "1")
print(f"capture cells: {len(cap)}; chain_ok: {ok}/{len(cap)}")
for h in ("0.3", "0.34", "0.4"):
    sub = [r for r in cap if r["hostile_frac"] == h and r["honest_turnout"] == "0.2"]
    if not sub: continue
    cr = sum(float(r["captured_any"]) for r in sub)/len(sub)
    print(f"  hostile={h} turnout=0.2: capture_rate={cr:.3f}")

deb = [r for r in load("deleg_blocs_sweep.csv") if r["deleg_pass"] not in ("", "-1")]
print(f"deleg-blocs cells: {len(deb)}")
for al in ("0.0", "1.0"):
    sub = [r for r in deb if r["aligned_frac"] == al]
    if not sub: continue
    n = len(sub)
    d = sum(float(r["deleg_pass"]) - float(r["baseline_pass"]) for r in sub)/n
    fid = sum(float(r["fidelity"]) for r in sub)/n
    print(f"  aligned={al}: delta_pass={d:+.3f} fidelity={fid:.3f}")

bench = load("verify_bench.csv")
if bench:
    first, last = bench[0], bench[-1]
    print(f"verify bench: L={first['chain_length']} -> "
          f"{first['verify_full_us_per_block']}us/block;"
          f" L={last['chain_length']} -> {last['verify_full_us_per_block']}us/block;"
          f" verify_block ~{last['verify_block_us']}us flat")
EOF
echo "=== NIGHT RUN 5 COMPLETE $(date -u +%FT%TZ) ==="
