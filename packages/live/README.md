# packages/live — near-live paper pilot

Fetches the latest **DE-LU** day-ahead prices and day-ahead load/solar/wind
forecasts from Energy-Charts (CC BY 4.0), runs an **ex-ante** ML forecast +
dispatch schedule for the next delivery day, and paper-trades the last ~14
completed days with decisions locked from information available **before**
each delivery day.

**Paper trading only.** No exchange order APIs. No real bids.

```bash
# from the umbrella repo root
python -m pip install -e packages/live -e packages/forecast \
  # or from the repo root: pip install -e ".[dev]"
python packages/live/scripts/run_live_pilot.py
```

Committed summary: `results/live/` at the umbrella root. Event streams under
`packages/live/results/` are gitignored.

The pilot fee toggle (`LivePilotConfig.apply_costs`, default on) reports gross mid-price P&L and net-of-ASSUMED-cost P&L. When on, ML/PF schedules use the cost-aware LP. Paper trading only.
