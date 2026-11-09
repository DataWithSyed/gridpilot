#!/usr/bin/env python3
"""Walk-forward forecast MAE + plug ML strategies into the paper agent.

Uses Energy-Charts cache from gridpilot-core / gridpilot-data when present.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UMBRELLA = ROOT.parents[1]
GP = UMBRELLA.parent
for p in (
    ROOT / "src",
    GP / "gridpilot-core" / "src",
    GP / "gridpilot-strategies" / "src",
    GP / "gridpilot-data" / "src",
    GP / "gridpilot-risk" / "src",
):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gridpilot_core.agent import PaperAgent
from gridpilot_core.battery import BatteryConfig
from gridpilot_core.risk import RiskLimits
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage
from gridpilot_forecast.features import daily_panel
from gridpilot_forecast.forecaster import WalkForwardQuantileForecast
from gridpilot_forecast.models import EnsembleQuantile, NaiveDayAhead, mae
from gridpilot_forecast.strategy import MLForecastDrivenLP, MLRiskAwareForecastLP
from gridpilot_strategies.forecast_lp import ForecastDrivenLP, RiskAwareForecastLP

try:
    from gridpilot_data.adapters import EnergyChartsAdapter

    def load_prices(start, end, cache):
        return EnergyChartsAdapter(cache_dir=cache).fetch_day_ahead_prices(start, end)
except Exception:
    from gridpilot_core.data_replay import fetch_day_ahead_prices as _fetch

    def load_prices(start, end, cache):
        return _fetch(start, end, cache_dir=cache)


def historical_cvar(s, alpha=0.05):
    s = pd.Series(s).dropna()
    if s.empty:
        return float("nan")
    q = s.quantile(alpha)
    return float(-(s[s <= q].mean()))


def max_drawdown(equity: pd.Series) -> float:
    eq = equity.astype(float)
    peak = eq.cummax()
    dd = peak - eq
    return float(dd.max()) if len(dd) else float("nan")


def forecast_mae_table(prices: pd.Series, lookback_days: int = 45) -> dict:
    pan = daily_panel(prices)
    days = list(pan.index)
    naive = NaiveDayAhead()
    rows = {"naive": [], "ensemble": []}
    # Walk-forward: for each day with enough history, refit ensemble on prior days
    last_fit = None
    model = None
    for i, day in enumerate(days):
        train = [d for d in days[:i] if not pan.loc[d].isna().any()]
        if len(train) < 14:
            continue
        train = train[-lookback_days:]
        if model is None or last_fit is None or (day - last_fit).days >= 1:
            model = EnsembleQuantile().fit(pan, train)
            last_fit = day
        y = pan.loc[day].to_numpy(float)
        if pan.loc[day].isna().any():
            continue
        npred = naive.predict_day(pan, day)
        epred = model.predict_day(pan, day) if model is not None else None
        if npred is not None:
            rows["naive"].append(mae(npred, y))
        if epred is not None and 0.50 in epred:
            rows["ensemble"].append(mae(epred[0.50], y))
    return {
        k: {
            "n_days": len(v),
            "mae_eur_mwh": float(np.mean(v)) if v else None,
            "mae_p50": float(np.median(v)) if v else None,
        }
        for k, v in rows.items()
    }


def run_agent(name, strat, prices, batt, risk):
    res = PaperAgent(batt, strat, risk).run(prices)
    daily = res.daily
    return {
        "final_cash_eur": float(res.summary["final_cash_eur"]),
        "n_days": int(len(daily)),
        "daily_pnl_p10": float(daily.quantile(0.1)) if len(daily) else None,
        "daily_pnl_p50": float(daily.quantile(0.5)) if len(daily) else None,
        "daily_pnl_p90": float(daily.quantile(0.9)) if len(daily) else None,
        "cvar_5pct_loss_daily": historical_cvar(daily),
        "max_drawdown_eur": max_drawdown(res.equity_eur),
        "cycles": float(res.summary.get("total_cycles", float("nan"))),
        "killed": bool(res.summary.get("killed", False)),
    }


def main():
    start, end = "2026-08-01", "2026-10-15"
    cache = GP / "gridpilot-core" / "data" / "cache"
    if not cache.exists():
        cache = GP / "gridpilot-data" / "data" / "cache"
    prices = load_prices(start, end, cache)
    mae_tbl = forecast_mae_table(prices)
    batt = BatteryConfig(power_mw=1.0, energy_mwh=2.0)
    risk = RiskLimits(max_cycles_per_day=2.0, max_drawdown_eur=5000.0)
    strategies = {
        "threshold_arbitrage": ThresholdArbitrage(),
        "forecast_driven_lp": ForecastDrivenLP(),
        "risk_aware_forecast_lp": RiskAwareForecastLP(),
        "ml_forecast_driven_lp": MLForecastDrivenLP(lookback_days=45, refit_every_days=3),
        "ml_risk_aware_forecast_lp": MLRiskAwareForecastLP(lookback_days=45, refit_every_days=3),
        "perfect_foresight_daily": PerfectForesightDaily(),
    }
    rows = {}
    for name, strat in strategies.items():
        print(f"running {name} ...", flush=True)
        rows[name] = run_agent(name, strat, prices, batt, risk)
    pf = rows["perfect_foresight_daily"]["final_cash_eur"]
    th = rows["threshold_arbitrage"]["final_cash_eur"]
    for r in rows.values():
        r["capture_vs_pf_pct"] = 100.0 * r["final_cash_eur"] / pf if pf else None
        r["vs_threshold_pct"] = 100.0 * r["final_cash_eur"] / th if th else None
    out = {
        "window": {"start": start, "end": end, "n_hours": int(len(prices))},
        "forecast_mae": mae_tbl,
        "strategies": rows,
        "limitations": [
            "Price-only LEAR-lite / QuantileGBM (no TSO load/wind features)",
            "Hourly resample of 15-min Energy-Charts MTU",
            "No fees/slippage; paper trading only",
            "Short sample (~2.5 months) limits ML train history",
        ],
        "attribution": "Energy-Charts / SMARD — CC BY 4.0",
    }
    dest = ROOT / "results" / "forecast_eval.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
