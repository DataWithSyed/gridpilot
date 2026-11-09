#!/usr/bin/env python3
"""12-month fundamentals + conformal forecast eval and strategy backtest (paper only).

Uses gitignored Energy-Charts cache (CC BY 4.0). Light memory: weekly ML refits,
one strategy at a time, small GBM trees.
"""
from __future__ import annotations

import gc
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
    UMBRELLA / "packages" / "backtest" / "src",
    GP / "gridpilot-core" / "src",
    GP / "gridpilot-strategies" / "src",
    GP / "gridpilot-data" / "src",
    GP / "gridpilot-risk" / "src",
):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gridpilot_backtest.metrics import block_bootstrap_mean_diff_ci, historical_cvar, max_drawdown
from gridpilot_core.agent import PaperAgent
from gridpilot_core.battery import BatteryConfig
from gridpilot_core.risk import RiskLimits
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage
from gridpilot_forecast.conformal import coverage, reliability_table
from gridpilot_forecast.features import daily_panel
from gridpilot_forecast.forecaster import WalkForwardQuantileForecast
from gridpilot_forecast.fundamentals import build_fundamentals_panels, load_fundamentals, slice_window
from gridpilot_forecast.models import EnsembleQuantile, NaiveDayAhead, mae
from gridpilot_forecast.strategy import MLForecastDrivenLP, MLRiskAwareForecastLP
from gridpilot_strategies.forecast_lp import ForecastDrivenLP, RiskAwareForecastLP

START = "2025-11-01"
END = "2026-10-30"
LOOKBACK = 90
REFIT = 7


def _berlin_price_series(df: pd.DataFrame) -> pd.Series:
    s = df["price"].astype(float).copy()
    s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Berlin")
    s = s.resample("h").mean()
    return s.rename("da_price_eur_mwh")


def forecast_eval(prices: pd.Series, fund: dict, lookback: int = LOOKBACK) -> dict:
    pan = daily_panel(prices)
    days = list(pan.index)
    naive = NaiveDayAhead()
    rows = {"naive": [], "ensemble_fund_raw": [], "ensemble_fund_cqr": []}
    y_hours, lo_raw, hi_raw, lo_c, hi_c = [], [], [], [], []
    p10s, p50s, p90s = [], [], []
    model = None
    last_fit = None
    from gridpilot_forecast.conformal import RollingCQR

    cqr = RollingCQR(alpha=0.20, window_days=60, delay=2)
    last_raw = None
    last_day = None
    for i, day in enumerate(days):
        train = [d for d in days[:i] if not pan.loc[d].isna().any()]
        if len(train) < 21:
            continue
        train = train[-lookback:]
        if model is None or last_fit is None or (day - last_fit).days >= REFIT:
            model = EnsembleQuantile(use_fundamentals=True).fit(pan, train, fund=fund)
            last_fit = day
            gc.collect()
        # Observe previous day for CQR
        if last_raw is not None and last_day is not None and last_day in pan.index:
            if last_day not in cqr._day_scores:
                cqr.observe_day(last_day, pan.loc[last_day].to_numpy(float), last_raw[0.10], last_raw[0.90])
        y = pan.loc[day].to_numpy(float)
        if pan.loc[day].isna().any():
            continue
        npred = naive.predict_day(pan, day)
        epred = model.predict_day(pan, day) if model is not None else None
        if npred is not None:
            rows["naive"].append(mae(npred, y))
        if epred is not None and 0.50 in epred:
            rows["ensemble_fund_raw"].append(mae(epred[0.50], y))
            cal = cqr.calibrate(day, epred)
            rows["ensemble_fund_cqr"].append(mae(cal[0.50], y))
            y_hours.append(y)
            lo_raw.append(epred[0.10])
            hi_raw.append(epred[0.90])
            lo_c.append(cal[0.10])
            hi_c.append(cal[0.90])
            p10s.append(cal[0.10])
            p50s.append(cal[0.50])
            p90s.append(cal[0.90])
            last_raw = {q: np.asarray(v, float).copy() for q, v in epred.items()}
            last_day = day
    out = {
        k: {
            "n_days": len(v),
            "mae_eur_mwh": float(np.mean(v)) if v else None,
            "mae_p50": float(np.median(v)) if v else None,
        }
        for k, v in rows.items()
    }
    if y_hours:
        y = np.concatenate(y_hours)
        out["calibration"] = {
            "raw_coverage_80": coverage(y, np.concatenate(lo_raw), np.concatenate(hi_raw)),
            "cqr_coverage_80": coverage(y, np.concatenate(lo_c), np.concatenate(hi_c)),
            "cqr_reliability": {
                str(k): v
                for k, v in reliability_table(
                    y,
                    {
                        0.10: np.concatenate(p10s),
                        0.50: np.concatenate(p50s),
                        0.90: np.concatenate(p90s),
                    },
                ).items()
            },
            "n_hours": int(len(y)),
            "nominal_80": 0.80,
        }
    return out


def run_agent(name, strat, prices, batt_kw, risk_kw):
    batt = BatteryConfig(**batt_kw)
    risk = RiskLimits(**risk_kw)
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
        "_daily": daily,
        "_equity": res.equity_eur,
    }


def main():
    cache = ROOT / "data" / "cache" / "de_lu_hourly.csv.gz"
    print(f"loading {cache}", flush=True)
    raw = load_fundamentals(cache)
    raw = slice_window(raw, START, END)
    print(f"window rows={len(raw)} {raw.index.min()} → {raw.index.max()}", flush=True)
    fund = build_fundamentals_panels(raw)
    prices = _berlin_price_series(raw)
    # Drop incomplete last hour if any
    prices = prices.dropna()
    print(f"prices hours={len(prices)} mean={prices.mean():.2f}", flush=True)

    print("forecast MAE + calibration ...", flush=True)
    mae_tbl = forecast_eval(prices, fund)
    print(json.dumps(mae_tbl, indent=2), flush=True)
    gc.collect()

    batt_kw = {"power_mw": 1.0, "energy_mwh": 2.0}
    risk_kw = {"max_cycles_per_day": 2.0, "max_drawdown_eur": 20000.0}

    strategies = [
        ("threshold_arbitrage", lambda: ThresholdArbitrage()),
        ("forecast_driven_lp", lambda: ForecastDrivenLP()),
        ("risk_aware_forecast_lp", lambda: RiskAwareForecastLP()),
        (
            "ml_forecast_driven_lp",
            lambda: MLForecastDrivenLP(
                lookback_days=LOOKBACK,
                refit_every_days=REFIT,
                use_fundamentals=True,
                calibrate=True,
                fundamentals=fund,
            ),
        ),
        (
            "ml_risk_aware_forecast_lp",
            lambda: MLRiskAwareForecastLP(
                lookback_days=LOOKBACK,
                refit_every_days=REFIT,
                use_fundamentals=True,
                calibrate=True,
                fundamentals=fund,
            ),
        ),
        ("perfect_foresight_daily", lambda: PerfectForesightDaily()),
    ]

    rows = {}
    dailies = {}
    for name, factory in strategies:
        print(f"running {name} ...", flush=True)
        strat = factory()
        r = run_agent(name, strat, prices, batt_kw, risk_kw)
        dailies[name] = r.pop("_daily")
        r.pop("_equity", None)
        rows[name] = r
        del strat
        gc.collect()
        print(
            f"  cash={r['final_cash_eur']:.2f} P50={r['daily_pnl_p50']:.2f} CVaR5={r['cvar_5pct_loss_daily']:.2f}",
            flush=True,
        )

    pf = rows["perfect_foresight_daily"]["final_cash_eur"]
    th = rows["threshold_arbitrage"]["final_cash_eur"]
    for r in rows.values():
        r["capture_vs_pf_pct"] = 100.0 * r["final_cash_eur"] / pf if pf else None
        r["vs_threshold_pct"] = 100.0 * r["final_cash_eur"] / th if th else None

    # Bootstrap CIs of mean daily PnL vs threshold
    boot = {}
    th_daily = dailies["threshold_arbitrage"]
    for name, daily in dailies.items():
        if name == "threshold_arbitrage":
            continue
        boot[name] = block_bootstrap_mean_diff_ci(daily, th_daily, block=7, n_boot=400, alpha=0.10, seed=0)

    out = {
        "window": {
            "start": START,
            "end": END,
            "n_hours": int(len(prices)),
            "da_mean_eur_mwh": float(prices.mean()),
            "da_min": float(prices.min()),
            "da_max": float(prices.max()),
            "neg_hour_pct": float((prices < 0).mean() * 100),
        },
        "forecast_mae": mae_tbl,
        "strategies": rows,
        "bootstrap_vs_threshold": boot,
        "assumptions": [
            "ML lookback_days=90, refit_every_days=7 (ASSUMED compute tradeoff)",
            "CQR alpha=0.20, window=60d, delay=2",
            "Day-ahead TSO forecasts from Energy-Charts public_power_forecast (ex-ante)",
            "Hourly mean of native 15-min MTU where applicable",
            "No fees/slippage; paper trading only",
            "1 MW / 2 MWh battery; max 2 cycles/day; drawdown stop 20k EUR",
        ],
        "attribution": "Energy-Charts / SMARD — CC BY 4.0",
        "paper_trading_only": True,
    }
    dest = ROOT / "results" / "long_window_eval.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    # Also write backtest package results for the dashboard
    bt = UMBRELLA / "packages" / "backtest" / "results" / "backtest.json"
    bt.parent.mkdir(parents=True, exist_ok=True)
    bt.write_text(json.dumps(out, indent=2), encoding="utf-8")
    # CSV table
    import csv

    csv_path = UMBRELLA / "packages" / "backtest" / "results" / "backtest.csv"
    fields = [
        "strategy",
        "final_cash_eur",
        "capture_vs_pf_pct",
        "daily_pnl_p10",
        "daily_pnl_p50",
        "daily_pnl_p90",
        "cvar_5pct_loss_daily",
        "max_drawdown_eur",
        "cycles",
        "killed",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for name, r in rows.items():
            w.writerow({"strategy": name, **r})
    print(json.dumps({k: v for k, v in out.items() if k != "bootstrap_vs_threshold"}, indent=2))
    print("bootstrap_vs_threshold:", json.dumps(boot, indent=2))
    print(f"wrote {dest} and {bt}")


if __name__ == "__main__":
    main()
