#!/usr/bin/env bash
# One-command paper simulator quickstart (no real orders).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev,ui]"
gridpilot-sim run --scenario normal --speed 0 --seed 0
echo "Dashboard:  streamlit run packages/simulator/src/gridpilot_simulator/dashboard.py"
echo "Or:         gridpilot-sim dashboard"
echo "Reports:    packages/simulator/results/demo_report.html  demo_dashboard.png"
echo "Paper trading only — not real-money performance."
