#!/usr/bin/env python3
"""Fees/slippage/degradation sweep + Mondrian CQR + equity figure (paper only).

Memory-light: one strategy at a time; cost scenarios are accounting on saved fills.
Window: 2025-11-01 → 2026-10-30. Never places real orders.
"""
from __future__ import annotations

import csv
import gc
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UMBRELLA = ROOT.parents[1]
GP = UMBRELLA  # in-repo packages/ (legacy name kept for cache fallbacks)
import sys as _sys
_sys.path.insert(0, str(UMBRELLA / "packages"))
from _srcpaths import add_src_paths, default_cache
add_src_paths(UMBRELLA)

from gridpilot_backtest.costs import (
    COST_SOURCES,
    DEFAULT_COST_SWEEP,
    ExecutionCosts,
    ZERO_COSTS,
    apply_costs_to_actions,
    cost_sensitivity_table,
)
from gridpilot_backtest.equity_plot import equity_and_drawdown_figure
from gridpilot_backtest.metrics import block_bootstrap_mean_diff_ci, historical_cvar, max_drawdown
from gridpilot_core.agent import PaperAgent
from gridpilot_core.battery import BatteryConfig
from gridpilot_core.risk import RiskLimits
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage
from gridpilot_forecast.conformal import (
    MondrianAsymmetricCQR,
    RollingCQR,
    coverage,
    hour_bucket,
    reliability_table,
    residual_load_regime,
)
from gridpilot_forecast.features import daily_panel
from gridpilot_forecast.fundamentals import build_fundamentals_panels, load_fundamentals, slice_window
from gridpilot_forecast.models import EnsembleQuantile, NaiveDayAhead, mae
from gridpilot_forecast.strategy import MLForecastDrivenLP, MLRiskAwareForecastLP
from gridpilot_strategies.forecast_lp import ForecastDrivenLP, RiskAwareForecastLP

START = "2025-11-01"
END = "2026-10-30"
LOOKBACK = 90
REFIT = 7

BT_RESULTS = UMBRELLA / "packages" / "backtest" / "results"
BT_FIG = UMBRELLA / "packages" / "backtest" / "figures"
FC_RESULTS = ROOT / "results"
DUMP = BT_RESULTS / "dumps"


def _berlin_price_series(df: pd.DataFrame) -> pd.Series:
    s = df["price"].astype(float).copy()
    s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Berlin")
    return s.resample("h").mean().rename("da_price_eur_mwh").dropna()


def _rl_edges(fund: dict) -> tuple[float, float] | None:
    if "residual_load_fc" not in fund:
        return None
    daily = fund["residual_load_fc"].mean(axis=1).dropna()
    if len(daily) < 30:
        return None
    q33, q66 = np.nanpercentile(daily.to_numpy(float), [33.3, 66.6])
    return float(q33), float(q66)


def forecast_eval_mondrian(prices: pd.Series, fund: dict) -> dict:
    pan = daily_panel(prices)
    days = list(pan.index)
    edges = _rl_edges(fund)
    naive = NaiveDayAhead()
    rows = {"naive": [], "ensemble_fund_raw": [], "cqr_rolling": [], "cqr_mondrian": []}
    y_all, lo_raw, hi_raw = [], [], []
    lo_r, hi_r, p10_r, p50_r, p90_r = [], [], [], [], []
    lo_m, hi_m, p10_m, p50_m, p90_m = [], [], [], [], []
    model = None
    last_fit = None
    rolling = RollingCQR(alpha=0.20, window_days=60, delay=2)
    mondrian = MondrianAsymmetricCQR(alpha=0.20, window_days=60, delay=2)
    last_raw = None
    last_day = None

    for i, day in enumerate(days):
        train = [d for d in days[:i] if not pan.loc[d].isna().any()]
        if len(train) < 21:
            continue
        train = train[-LOOKBACK:]
        if model is None or last_fit is None or (day - last_fit).days >= REFIT:
            model = EnsembleQuantile(use_fundamentals=True).fit(pan, train, fund=fund)
            last_fit = day
            gc.collect()
        if last_raw is not None and last_day is not None and last_day in pan.index:
            y_prev = pan.loc[last_day].to_numpy(float)
            if last_day not in rolling._day_scores:
                rolling.observe_day(last_day, y_prev, last_raw[0.10], last_raw[0.90])
            if last_day not in mondrian._lower:
                if edges is not None and "residual_load_fc" in fund and last_day in fund["residual_load_fc"].index:
                    day_rl = float(np.nanmean(fund["residual_load_fc"].loc[last_day].to_numpy(float)))
                    reg = residual_load_regime(day_rl, edges)
                    mondrian.observe_day(
                        last_day, y_prev, last_raw[0.10], last_raw[0.90],
                        regime=reg, q_p50=last_raw.get(0.50),
                    )
                else:
                    hour_regs = np.array([hour_bucket(h) for h in range(len(y_prev))])
                    mondrian.observe_day(
                        last_day, y_prev, last_raw[0.10], last_raw[0.90],
                        q_p50=last_raw.get(0.50), hour_regimes=hour_regs,
                    )
        y = pan.loc[day].to_numpy(float)
        if pan.loc[day].isna().any():
            continue
        npred = naive.predict_day(pan, day)
        epred = model.predict_day(pan, day) if model is not None else None
        if npred is not None:
            rows["naive"].append(mae(npred, y))
        if epred is not None and 0.50 in epred:
            rows["ensemble_fund_raw"].append(mae(epred[0.50], y))
            cal_r = rolling.calibrate(day, epred)
            if edges is not None and "residual_load_fc" in fund and day in fund["residual_load_fc"].index:
                day_rl = float(np.nanmean(fund["residual_load_fc"].loc[day].to_numpy(float)))
                reg = residual_load_regime(day_rl, edges)
                cal_m = mondrian.calibrate(day, epred, regime=reg)
            else:
                hour_regs = np.array([hour_bucket(h) for h in range(len(y))])
                cal_m = mondrian.calibrate(day, epred, hour_regimes=hour_regs)
            rows["cqr_rolling"].append(mae(cal_r[0.50], y))
            rows["cqr_mondrian"].append(mae(cal_m[0.50], y))
            y_all.append(y)
            lo_raw.append(epred[0.10]); hi_raw.append(epred[0.90])
            lo_r.append(cal_r[0.10]); hi_r.append(cal_r[0.90])
            p10_r.append(cal_r[0.10]); p50_r.append(cal_r[0.50]); p90_r.append(cal_r[0.90])
            lo_m.append(cal_m[0.10]); hi_m.append(cal_m[0.90])
            p10_m.append(cal_m[0.10]); p50_m.append(cal_m[0.50]); p90_m.append(cal_m[0.90])
            last_raw = {q: np.asarray(v, float).copy() for q, v in epred.items()}
            last_day = day

    out = {
        k: {"n_days": len(v), "mae_eur_mwh": float(np.mean(v)) if v else None}
        for k, v in rows.items()
    }
    if y_all:
        y = np.concatenate(y_all)
        out["calibration"] = {
            "raw_coverage_80": coverage(y, np.concatenate(lo_raw), np.concatenate(hi_raw)),
            "rolling_cqr_coverage_80": coverage(y, np.concatenate(lo_r), np.concatenate(hi_r)),
            "mondrian_cqr_coverage_80": coverage(y, np.concatenate(lo_m), np.concatenate(hi_m)),
            "rolling_reliability": {
                str(k): v
                for k, v in reliability_table(
                    y,
                    {0.10: np.concatenate(p10_r), 0.50: np.concatenate(p50_r), 0.90: np.concatenate(p90_r)},
                ).items()
            },
            "mondrian_reliability": {
                str(k): v
                for k, v in reliability_table(
                    y,
                    {0.10: np.concatenate(p10_m), 0.50: np.concatenate(p50_m), 0.90: np.concatenate(p90_m)},
                ).items()
            },
            "n_hours": int(len(y)),
            "nominal_80": 0.80,
            "rl_edges": list(edges) if edges else None,
        }
        # Reliability / coverage plot (light)
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(6, 4))
            labels = ["raw", "rolling CQR", "Mondrian CQR"]
            vals = [
                out["calibration"]["raw_coverage_80"],
                out["calibration"]["rolling_cqr_coverage_80"],
                out["calibration"]["mondrian_cqr_coverage_80"],
            ]
            ax.bar(labels, [100 * v for v in vals], color=["#999", "#4C78A8", "#F58518"])
            ax.axhline(80, color="k", ls="--", lw=1, label="nominal 80%")
            ax.set_ylabel("Coverage %")
            ax.set_title("80% interval coverage (long window)")
            ax.legend(frameon=False)
            fig.tight_layout()
            dest = BT_FIG / "coverage_calibration.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(dest, dpi=120)
            plt.close(fig)
            out["calibration"]["coverage_figure"] = str(dest.relative_to(UMBRELLA))
        except Exception as exc:  # pragma: no cover
            out["calibration"]["coverage_figure_error"] = str(exc)
    return out


def run_agent_gross(name, strat, prices):
    """Run with degradation=0 so cost layer owns all wear/fee/slip accounting."""
    batt = BatteryConfig(power_mw=1.0, energy_mwh=2.0, degradation_eur_per_mwh=0.0)
    risk = RiskLimits(max_cycles_per_day=2.0, max_drawdown_eur=20000.0)
    res = PaperAgent(batt, strat, risk).run(prices)
    return res


def main():
    BT_RESULTS.mkdir(parents=True, exist_ok=True)
    BT_FIG.mkdir(parents=True, exist_ok=True)
    FC_RESULTS.mkdir(parents=True, exist_ok=True)
    DUMP.mkdir(parents=True, exist_ok=True)

    cache = ROOT / "data" / "cache" / "de_lu_hourly.csv.gz"
    print(f"loading {cache}", flush=True)
    raw = slice_window(load_fundamentals(cache), START, END)
    fund = build_fundamentals_panels(raw)
    prices = _berlin_price_series(raw)
    print(f"prices hours={len(prices)} mean={prices.mean():.2f}", flush=True)

    print("Mondrian vs rolling CQR calibration ...", flush=True)
    mae_tbl = forecast_eval_mondrian(prices, fund)
    print(json.dumps(mae_tbl, indent=2), flush=True)
    gc.collect()

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
        (
            "ml_mondrian_forecast_driven_lp",
            lambda: MLForecastDrivenLP(
                lookback_days=LOOKBACK,
                refit_every_days=REFIT,
                use_fundamentals=True,
                calibrate=True,
                calibrator_kind="mondrian",
                fundamentals=fund,
            ),
        ),
        ("perfect_foresight_daily", lambda: PerfectForesightDaily()),
    ]

    actions_by = {}
    cycles_by = {}
    killed_by = {}
    gross_equity = {}
    for name, factory in strategies:
        print(f"running gross (deg=0) {name} ...", flush=True)
        strat = factory()
        res = run_agent_gross(name, strat, prices)
        acts = res.actions.copy()
        acts_path = DUMP / f"{name}_actions.parquet"
        try:
            acts.to_parquet(acts_path)
        except Exception:
            acts.to_csv(DUMP / f"{name}_actions.csv", index=False)
        eq_path = DUMP / f"{name}_equity.csv"
        res.equity_eur.to_csv(eq_path, header=True)
        actions_by[name] = acts
        cycles_by[name] = float(res.summary.get("total_cycles", float("nan")))
        killed_by[name] = bool(res.summary.get("killed", False))
        gross_equity[name] = res.equity_eur
        print(
            f"  gross_cash={res.summary['final_cash_eur']:.2f} cycles={cycles_by[name]:.1f}",
            flush=True,
        )
        del strat, res
        gc.collect()

    # Cost sensitivity
    print("cost sensitivity ...", flush=True)
    sens = cost_sensitivity_table(
        actions_by, DEFAULT_COST_SWEEP, cycles_by_strategy=cycles_by, killed_by_strategy=killed_by
    )
    sens_path = BT_RESULTS / "cost_sensitivity.csv"
    sens.to_csv(sens_path, index=False)

    # Primary net-of-costs table = base scenario
    base = ExecutionCosts(0.05, 0.50, 5.0, label="base")
    net_rows = {}
    net_equity = {}
    net_daily = {}
    for name, acts in actions_by.items():
        priced = apply_costs_to_actions(acts, base)
        m = priced["metrics"]
        m["cycles"] = cycles_by[name]
        m["killed"] = killed_by[name]
        m["total_fees_eur"] = priced["total_fees_eur"]
        m["total_slippage_eur"] = priced["total_slippage_eur"]
        m["total_degradation_eur"] = priced["total_degradation_eur"]
        m["throughput_mwh"] = priced["throughput_mwh"]
        net_rows[name] = m
        net_equity[name] = priced["equity_eur"]
        net_daily[name] = priced["daily"]

    pf = net_rows["perfect_foresight_daily"]["final_cash_eur"]
    th = net_rows["threshold_arbitrage"]["final_cash_eur"]
    for r in net_rows.values():
        r["capture_vs_pf_pct"] = 100.0 * r["final_cash_eur"] / pf if pf else None
        r["vs_threshold_pct"] = 100.0 * r["final_cash_eur"] / th if th else None

    boot = {}
    th_daily = net_daily["threshold_arbitrage"]
    for name, daily in net_daily.items():
        if name == "threshold_arbitrage":
            continue
        boot[name] = block_bootstrap_mean_diff_ci(daily, th_daily, block=7, n_boot=400, alpha=0.10, seed=0)

    # Equity figure (base costs)
    plot_names = [
        "threshold_arbitrage",
        "forecast_driven_lp",
        "ml_forecast_driven_lp",
        "ml_mondrian_forecast_driven_lp",
        "ml_risk_aware_forecast_lp",
        "perfect_foresight_daily",
    ]
    eq_fig = equity_and_drawdown_figure(
        {k: net_equity[k] for k in plot_names if k in net_equity},
        title="GridPilot equity net of fees/slippage/degradation (base ASSUMED)",
        outfile=BT_FIG / "equity_curve_net.png",
    )
    print(f"wrote {eq_fig}", flush=True)

    # Zero-cost reference for honesty vs prior published numbers
    zero_rows = {}
    for name, acts in actions_by.items():
        z = apply_costs_to_actions(acts, ZERO_COSTS)
        zero_rows[name] = {
            "final_cash_eur": z["final_cash_eur"],
            "capture_vs_pf_pct": None,
        }
    zpf = zero_rows["perfect_foresight_daily"]["final_cash_eur"]
    for r in zero_rows.values():
        r["capture_vs_pf_pct"] = 100.0 * r["final_cash_eur"] / zpf if zpf else None

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
        "strategies": net_rows,
        "strategies_zero_costs": zero_rows,
        "bootstrap_vs_threshold": boot,
        "cost_scenario_base": base.to_dict(),
        "cost_sources": COST_SOURCES,
        "cost_sensitivity_csv": str(sens_path.relative_to(UMBRELLA)),
        "equity_figure": "packages/backtest/figures/equity_curve_net.png",
        "coverage_figure": (mae_tbl.get("calibration") or {}).get("coverage_figure"),
        "assumptions": [
            "ML lookback_days=90, refit_every_days=7 (ASSUMED)",
            "Rolling CQR alpha=0.20 window=60d delay=2; Mondrian asymmetric + P50 shift",
            "Base costs ASSUMED: fee 0.05 €/MWh, slippage 0.50 €/MWh, degradation 5 €/MWh throughput",
            "Cost layer is accounting on fills; strategies do not re-optimise for fees",
            "Paper trading only — no live orders",
            "1 MW / 2 MWh; max 2 cycles/day; drawdown stop 20k EUR",
            "Optional FCR overlay: link only to de-bess-reserve-revenue-stacking (not co-optimised here)",
        ],
        "attribution": "Energy-Charts / SMARD — CC BY 4.0",
        "paper_trading_only": True,
        "note_prior_runs": (
            "Prior long-window README cash used core default degradation_eur_per_mwh=5 "
            "but fee=slippage=0. This run reports explicit zero vs base vs stress."
        ),
    }
    dest = FC_RESULTS / "costs_mondrian_equity.json"
    dest.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    bt = BT_RESULTS / "backtest.json"
    bt.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    csv_path = BT_RESULTS / "backtest.csv"
    fields = [
        "strategy", "final_cash_eur", "capture_vs_pf_pct",
        "daily_pnl_p10", "daily_pnl_p50", "daily_pnl_p90",
        "cvar_5pct_loss_daily", "max_drawdown_eur", "cycles", "killed",
        "total_fees_eur", "total_slippage_eur", "total_degradation_eur", "throughput_mwh",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for name, r in net_rows.items():
            w.writerow({"strategy": name, **r})
    print(json.dumps({"strategies": net_rows, "calibration": mae_tbl.get("calibration"), "boot": boot}, indent=2, default=float))
    print(f"wrote {dest} {bt} {sens_path}")


if __name__ == "__main__":
    main()
