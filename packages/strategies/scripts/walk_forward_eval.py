#!/usr/bin/env python3
"""Walk-forward evaluation: Threshold vs ForecastDriven vs RiskAware vs PerfectForesight.

Uses real Energy-Charts cache when available (from gridpilot-core or gridpilot-data),
otherwise fetches via gridpilot_data / gridpilot_core data_replay.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Prefer local editable installs
ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT.parent / "gridpilot-core"
DATA = ROOT.parent / "gridpilot-data"
RISK = ROOT.parent / "gridpilot-risk"
for p in (ROOT / "src", CORE / "src", DATA / "src", RISK / "src"):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gridpilot_core.agent import PaperAgent
from gridpilot_core.battery import BatteryConfig
from gridpilot_core.risk import RiskLimits
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage
from gridpilot_strategies.forecast_lp import ForecastDrivenLP, RiskAwareForecastLP

try:
    from gridpilot_data.adapters import EnergyChartsAdapter

    def load_prices(start: str, end: str, cache: Path) -> pd.Series:
        return EnergyChartsAdapter(cache_dir=cache).fetch_day_ahead_prices(start, end)

except Exception:
    from gridpilot_core.data_replay import fetch_day_ahead_prices

    def load_prices(start: str, end: str, cache: Path) -> pd.Series:
        return fetch_day_ahead_prices(start, end, cache_dir=cache)


try:
    from gridpilot_risk.var_cvar import distribution_summary, historical_cvar
except Exception:
    def distribution_summary(s):
        s = pd.Series(s).dropna()
        return {
            "p10": float(s.quantile(0.1)),
            "p50": float(s.quantile(0.5)),
            "p90": float(s.quantile(0.9)),
            "mean": float(s.mean()),
        }

    def historical_cvar(s, alpha=0.05):
        s = pd.Series(s).dropna()
        q = s.quantile(alpha)
        return float(-(s[s <= q].mean()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-08-01")
    ap.add_argument("--end", default="2026-10-15")
    ap.add_argument("--cache", type=Path, default=CORE / "data" / "cache")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "walk_forward.json")
    args = ap.parse_args()

    # Reuse core cache if present; also allow data cache
    cache = args.cache
    if not cache.exists():
        alt = DATA / "data" / "cache"
        cache = alt if alt.exists() else args.cache
    # Copy symlink/path: also try copying from core by pointing adapter there
    prices = load_prices(args.start, args.end, cache)
    # Warmup: strategies need history; evaluate on full sample but report honestly
    batt = BatteryConfig(power_mw=1.0, energy_mwh=2.0)
    risk = RiskLimits(max_cycles_per_day=2.0, max_drawdown_eur=5000.0)

    strategies = {
        "threshold_arbitrage": ThresholdArbitrage(),
        "forecast_driven_lp": ForecastDrivenLP(),
        "risk_aware_forecast_lp": RiskAwareForecastLP(),
        "perfect_foresight_daily": PerfectForesightDaily(),
    }
    rows = {}
    for name, strat in strategies.items():
        agent = PaperAgent(batt, strat, risk)
        res = agent.run(prices)
        daily = res.daily
        summ = distribution_summary(daily)
        rows[name] = {
            "final_cash_eur": float(res.summary.get("final_cash_eur", res.equity_eur.iloc[-1])),
            "n_days": int(len(daily)),
            "daily_pnl_mean": float(daily.mean()) if len(daily) else None,
            "daily_pnl_p10": float(daily.quantile(0.1)) if len(daily) else None,
            "daily_pnl_p50": float(daily.quantile(0.5)) if len(daily) else None,
            "daily_pnl_p90": float(daily.quantile(0.9)) if len(daily) else None,
            "cvar_5pct_loss_daily": historical_cvar(daily, 0.05) if len(daily) else None,
            "cycles": float(res.summary.get("total_cycles", float("nan"))),
            "killed": bool(res.summary.get("killed", False)),
            "extra": {k: summ.get(k) for k in ("var_5pct_loss", "cvar_5pct_loss") if k in summ},
        }

    pf = rows["perfect_foresight_daily"]["final_cash_eur"]
    th = rows["threshold_arbitrage"]["final_cash_eur"]
    for name, r in rows.items():
        r["capture_vs_pf_pct"] = (100.0 * r["final_cash_eur"] / pf) if pf else None
        r["vs_threshold_pct"] = (100.0 * r["final_cash_eur"] / th) if th else None

    out = {
        "window": {"start": args.start, "end": args.end, "n_hours": int(len(prices))},
        "battery": "1 MW / 2 MWh, eta 0.95/0.95, max 2 cycles/day",
        "price_stats": {
            "mean": float(prices.mean()),
            "min": float(prices.min()),
            "max": float(prices.max()),
        },
        "strategies": rows,
        "limitations": [
            "Hourly resample of 15-min Energy-Charts MTU",
            "No fees/slippage",
            "Forecast is rolling hour-of-day quantile climatology (not ML)",
            "In-sample walk over the same window used for lookback — early days are warm-up",
            "Paper trading only",
        ],
        "attribution": "Energy-Charts / SMARD — CC BY 4.0",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
