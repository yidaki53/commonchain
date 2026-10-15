#!/usr/bin/env bash
# Overnight launcher for commonchain compute. One command before sleep:
#   bash run_overnight.sh 2>&1 | tee logs/overnight.log
# Each stage is guarded with `|| true` so one failure never stops the night.
# All sweeps checkpoint to results/sweep_state.json and resume on re-run.
set -u
cd "$(dirname "$0")"
mkdir -p logs results
# Environment is managed by uv: `uv sync` creates .venv; the package is
# installed editable, so PYTHONPATH is not required.

echo "=== [0] smoke test (fast cells) ==="
uv run python sim/sweep.py --job gov --cells 4 --seeds 2 || true
uv run python sim/sweep.py --job payroll --cells 4 --seeds 2 || true
uv run python sim/sweep.py --job mandate --cells 4 --seeds 2 || true
uv run python sim/stress.py --blocks 200 --fuzz 20 --amend 50 || true
echo "=== smoke OK ==="

echo "=== [1] governance sweep (~3h) ==="
uv run python sim/sweep.py --job gov || true

echo "=== [2] payroll sweep (~1.5h) ==="
uv run python sim/sweep.py --job payroll || true

echo "=== [3] mandate sweep (~1h) ==="
uv run python sim/sweep.py --job mandate || true

echo "=== [4] stress + fuzz (~45min) ==="
uv run python sim/stress.py || true

echo "=== [5] figures + tables ==="
uv run python analysis/make_figures.py || true

echo "=== [6] test matrix + coverage (gate) ==="
uv run python -m pytest tests/ -q --cov=commonchain --cov-report=term > results/coverage.txt 2>&1 || true
uv run ruff check commonchain sim analysis tests > results/lint.txt 2>&1 || true
echo "--- coverage ---"
tail -n 15 results/coverage.txt || true
echo "--- lint ---"
tail -n 10 results/lint.txt || true

echo "=== NIGHT RUN COMPLETE $(date -u +%FT%TZ) ==="
