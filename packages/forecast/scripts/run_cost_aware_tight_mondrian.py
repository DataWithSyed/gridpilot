#!/usr/bin/env python3
"""Cost-aware LP + tight Mondrian CQR on the 12-month window (paper only).

Reuses prior gross dumps for non-reoptimised baselines when present.
Memory-light: one new strategy at a time.
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
    ExecutionCosts,
    ZERO_COSTS,
    apply_costs_to_actions,
    get_cost_preset,
)
from gridpilot_backtest.fees import RETRIEVAL_DATE, sourced_preset_components
from gridpilot_backtest.metrics import block_bootstrap_mean_diff_ci, max_drawdown
from gridpilot_core.agent import PaperAgent
from gridpilot_core.battery import BatteryConfig
from gridpilot_core.risk import RiskLimits
from gridpilot_forecast.conformal import (
    MondrianAsymmetricCQR,
    RollingCQR,
    build_tight_hour_regimes,
    coverage,
    hour_bucket,
    reliability_table,
    residual_load_regime,
)
from gridpilot_forecast.cost_aware_lp import CostAwarePerfectForesightDaily, MLCostAwareForecastDrivenLP
from gridpilot_forecast.features import daily_panel
from gridpilot_forecast.fundamentals import build_fundamentals_panels, load_fundamentals, slice_window
from gridpilot_forecast.models import EnsembleQuantile, NaiveDayAhead, mae

START = "2025-11-01"
END = "2026-10-30"
LOOKBACK = 90
REFIT = 7
# Overwritten in main() from --costs (default remains the assumed "base" preset).
BASE = ExecutionCosts(0.05, 0.50, 5.0, label="base")

BT_RESULTS = UMBRELLA / "packages" / "backtest" / "results"
BT_FIG = UMBRELLA / "packages" / "backtest" / "figures"
FC_RESULTS = ROOT / "results"
DUMP = BT_RESULTS / "dumps"


def _berlin_price_series(df: pd.DataFrame) -> pd.Series:
    s = df["price"].astype(float).copy()
    s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Berlin")
    return s.resample("h").mean().rename("da_price_eur_mwh").dropna()


def _rl_edges(fund: dict, *, hourly: bool = False):
    if "residual_load_fc" not in fund:
        return None
    rl = fund["residual_load_fc"]
    if hourly:
        vals = rl.to_numpy(float).ravel()
        vals = vals[np.isfinite(vals)]
        if len(vals) < 24 * 30:
            return None
    else:
        daily = rl.mean(axis=1).dropna()
        if len(daily) < 30:
            return None
        vals = daily.to_numpy(float)
    q33, q66 = np.nanpercentile(vals, [33.3, 66.6])
    return float(q33), float(q66)


def forecast_eval(prices: pd.Series, fund: dict) -> dict:
    pan = daily_panel(prices)
    days = list(pan.index)
    edges_d = _rl_edges(fund, hourly=False)
    edges_h = _rl_edges(fund, hourly=True)
    naive = NaiveDayAhead()
    rows = {"naive": [], "ensemble_fund_raw": [], "cqr_rolling": [], "cqr_mondrian": [], "cqr_tight": []}
    bags = {k: {"y": [], "lo": [], "hi": [], "p10": [], "p50": [], "p90": []} for k in ("raw", "roll", "mon", "tight")}
    model = None
    last_fit = None
    rolling = RollingCQR(alpha=0.20, window_days=60, delay=2)
    mondrian = MondrianAsymmetricCQR(alpha=0.20, window_days=60, delay=2)
    tight = MondrianAsymmetricCQR(alpha=0.20, window_days=60, delay=2)
    last_raw = None
    last_day = None

    def _store(bag, y, cal):
        bag["y"].append(y)
        bag["lo"].append(cal[0.10])
        bag["hi"].append(cal[0.90])
        bag["p10"].append(cal[0.10])
        bag["p50"].append(cal[0.50])
        bag["p90"].append(cal[0.90])

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
                if edges_d is not None and "residual_load_fc" in fund and last_day in fund["residual_load_fc"].index:
                    day_rl = float(np.nanmean(fund["residual_load_fc"].loc[last_day].to_numpy(float)))
                    mondrian.observe_day(
                        last_day, y_prev, last_raw[0.10], last_raw[0.90],
                        regime=residual_load_regime(day_rl, edges_d), q_p50=last_raw.get(0.50),
                    )
                else:
                    mondrian.observe_day(
                        last_day, y_prev, last_raw[0.10], last_raw[0.90],
                        q_p50=last_raw.get(0.50),
                        hour_regimes=np.array([hour_bucket(h) for h in range(len(y_prev))]),
                    )
            if last_day not in tight._lower:
                residual = None
                if edges_h is not None and "residual_load_fc" in fund and last_day in fund["residual_load_fc"].index:
                    residual = np.asarray(fund["residual_load_fc"].loc[last_day].to_numpy(float)).ravel()[: len(y_prev)]
                labs = build_tight_hour_regimes(
                    last_day, len(y_prev), price_panel=pan, residual_hourly=residual, rl_edges=edges_h
                )
                tight.observe_day(
                    last_day, y_prev, last_raw[0.10], last_raw[0.90],
                    q_p50=last_raw.get(0.50), hour_regimes=labs,
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
            if edges_d is not None and "residual_load_fc" in fund and day in fund["residual_load_fc"].index:
                day_rl = float(np.nanmean(fund["residual_load_fc"].loc[day].to_numpy(float)))
                cal_m = mondrian.calibrate(day, epred, regime=residual_load_regime(day_rl, edges_d))
            else:
                cal_m = mondrian.calibrate(
                    day, epred, hour_regimes=np.array([hour_bucket(h) for h in range(len(y))])
                )
            residual = None
            if edges_h is not None and "residual_load_fc" in fund and day in fund["residual_load_fc"].index:
                residual = np.asarray(fund["residual_load_fc"].loc[day].to_numpy(float)).ravel()[: len(y)]
            labs = build_tight_hour_regimes(
                day, len(y), price_panel=pan, residual_hourly=residual, rl_edges=edges_h
            )
            cal_t = tight.calibrate(day, epred, hour_regimes=labs)
            rows["cqr_rolling"].append(mae(cal_r[0.50], y))
            rows["cqr_mondrian"].append(mae(cal_m[0.50], y))
            rows["cqr_tight"].append(mae(cal_t[0.50], y))
            _store(bags["raw"], y, epred)
            _store(bags["roll"], y, cal_r)
            _store(bags["mon"], y, cal_m)
            _store(bags["tight"], y, cal_t)
            last_raw = {q: np.asarray(v, float).copy() for q, v in epred.items()}
            last_day = day

    def _cal(bag):
        if not bag["y"]:
            return {}
        y = np.concatenate(bag["y"])
        return {
            "coverage_80": coverage(y, np.concatenate(bag["lo"]), np.concatenate(bag["hi"])),
            "reliability": {
                str(k): v
                for k, v in reliability_table(
                    y,
                    {
                        0.10: np.concatenate(bag["p10"]),
                        0.50: np.concatenate(bag["p50"]),
                        0.90: np.concatenate(bag["p90"]),
                    },
                ).items()
            },
            "n_hours": int(len(y)),
        }

    out = {k: {"n_days": len(v), "mae_eur_mwh": float(np.mean(v)) if v else None} for k, v in rows.items()}
    out["calibration"] = {
        "raw": _cal(bags["raw"]),
        "rolling_cqr": _cal(bags["roll"]),
        "mondrian_cqr": _cal(bags["mon"]),
        "tight_mondrian_cqr": _cal(bags["tight"]),
        "nominal_80": 0.80,
    }
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4))
        labels = ["raw", "rolling CQR", "Mondrian", "tight Mondrian"]
        vals = [
            out["calibration"]["raw"].get("coverage_80"),
            out["calibration"]["rolling_cqr"].get("coverage_80"),
            out["calibration"]["mondrian_cqr"].get("coverage_80"),
            out["calibration"]["tight_mondrian_cqr"].get("coverage_80"),
        ]
        ax.bar(labels, [100 * v for v in vals], color=["#999", "#4C78A8", "#F58518", "#54A24B"])
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
    except Exception as exc:
        out["calibration"]["coverage_figure_error"] = str(exc)
    return out


def _load_dump(name: str) -> pd.DataFrame | None:
    pq = DUMP / f"{name}_actions.parquet"
    csvp = DUMP / f"{name}_actions.csv"
    if pq.exists():
        return pd.read_parquet(pq)
    if csvp.exists():
        return pd.read_csv(csvp)
    return None


def _metrics_from_priced(priced, cycles, killed):
    m = dict(priced["metrics"])
    m["cycles"] = cycles
    m["killed"] = killed
    m["total_fees_eur"] = priced["total_fees_eur"]
    m["total_slippage_eur"] = priced["total_slippage_eur"]
    m["total_degradation_eur"] = priced["total_degradation_eur"]
    m["throughput_mwh"] = priced["throughput_mwh"]
    return m, priced["equity_eur"], priced["daily"]


def run_agent(name, strat, prices, costs: ExecutionCosts):
    batt = BatteryConfig(power_mw=1.0, energy_mwh=2.0, degradation_eur_per_mwh=0.0)
    risk = RiskLimits(max_cycles_per_day=2.0, max_drawdown_eur=20000.0)
    res = PaperAgent(batt, strat, risk).run(prices)
    DUMP.mkdir(parents=True, exist_ok=True)
    try:
        res.actions.to_parquet(DUMP / f"{name}_actions.parquet")
    except Exception:
        res.actions.to_csv(DUMP / f"{name}_actions.csv", index=False)
    priced = apply_costs_to_actions(res.actions, costs)
    cycles = float(res.summary.get("total_cycles", float("nan")))
    killed = bool(res.summary.get("killed", False))
    m, eq, daily = _metrics_from_priced(priced, cycles, killed)
    return m, eq, daily, float(res.summary["final_cash_eur"])


def _parse_args(argv=None):
    import argparse

    p = argparse.ArgumentParser(description="Cost-aware LP backtest (paper only).")
    p.add_argument(
        "--costs",
        default="base",
        choices=("base", "assumed", "sourced", "zero"),
        help="Cost preset: assumed/base (0.05/0.50/5) or sourced (ECC 0.015, slip 0, deg still assumed).",
    )
    p.add_argument(
        "--skip-forecast",
        action="store_true",
        help="Reuse packages/forecast/results/cost_aware_tight_mondrian.json forecast_mae if present.",
    )
    return p.parse_args(argv)


def main(argv=None):
    global BASE
    args = _parse_args(argv)
    BASE = get_cost_preset(args.costs)
    preset = BASE.label
    suffix = "" if preset in {"base", "assumed"} else f"_{preset}"
    print(f"cost preset={preset} fee={BASE.fee_eur_per_mwh} slip={BASE.slippage_eur_per_mwh} deg={BASE.degradation_eur_per_mwh}", flush=True)

    BT_RESULTS.mkdir(parents=True, exist_ok=True)
    BT_FIG.mkdir(parents=True, exist_ok=True)
    FC_RESULTS.mkdir(parents=True, exist_ok=True)

    cache = ROOT / "data" / "cache" / "de_lu_hourly.csv.gz"
    print(f"loading {cache}", flush=True)
    raw = slice_window(load_fundamentals(cache), START, END)
    fund = build_fundamentals_panels(raw)
    prices = _berlin_price_series(raw)
    print(f"prices hours={len(prices)} mean={prices.mean():.2f}", flush=True)

    mae_tbl = None
    prior = FC_RESULTS / "cost_aware_tight_mondrian.json"
    if args.skip_forecast and prior.exists():
        try:
            mae_tbl = json.loads(prior.read_text(encoding="utf-8")).get("forecast_mae")
            print("reused forecast_mae from prior cost_aware_tight_mondrian.json", flush=True)
        except Exception as exc:
            print(f"could not reuse forecast_mae ({exc}); running eval", flush=True)
            mae_tbl = None
    if mae_tbl is None:
        print("forecast eval (rolling / Mondrian / tight Mondrian) ...", flush=True)
        mae_tbl = forecast_eval(prices, fund)
        print(json.dumps(mae_tbl, indent=2, default=float), flush=True)
    gc.collect()

    net_rows = {}
    net_daily = {}
    reused = []
    for name in (
        "threshold_arbitrage",
        "ml_forecast_driven_lp",
        "ml_mondrian_forecast_driven_lp",
        "perfect_foresight_daily",
    ):
        acts = _load_dump(name)
        if acts is None:
            print(f"missing dump {name} — skip reuse", flush=True)
            continue
        priced = apply_costs_to_actions(acts, BASE)
        cycles = float("nan")
        m, eq, daily = _metrics_from_priced(priced, cycles, False)
        net_rows[name] = m
        net_daily[name] = daily
        reused.append(name)
        print(f"reused {name} net_cash={m['final_cash_eur']:.2f}", flush=True)
        del acts, priced
        gc.collect()

    ca_ml = "ml_cost_aware_forecast_driven_lp" + suffix
    ca_tight = "ml_cost_aware_tight_mondrian" + suffix
    ca_pf = "cost_aware_perfect_foresight_daily" + suffix
    new_strats = [
        (
            ca_ml,
            lambda: MLCostAwareForecastDrivenLP(
                lookback_days=LOOKBACK,
                refit_every_days=REFIT,
                use_fundamentals=True,
                calibrate=True,
                calibrator_kind="rolling",
                fundamentals=fund,
                costs=BASE,
            ),
        ),
        (
            ca_tight,
            lambda: MLCostAwareForecastDrivenLP(
                name=ca_tight,
                lookback_days=LOOKBACK,
                refit_every_days=REFIT,
                use_fundamentals=True,
                calibrate=True,
                calibrator_kind="mondrian",
                mondrian_mode="tight",
                fundamentals=fund,
                costs=BASE,
            ),
        ),
        (ca_pf, lambda: CostAwarePerfectForesightDaily(costs=BASE)),
    ]
    for name, factory in new_strats:
        print(f"running {name} ...", flush=True)
        strat = factory()
        m, eq, daily, gross = run_agent(name, strat, prices, BASE)
        m["gross_cash_deg0_eur"] = gross
        net_rows[name] = m
        net_daily[name] = daily
        print(f"  net_cash={m['final_cash_eur']:.2f} cycles={m['cycles']:.1f}", flush=True)
        del strat
        gc.collect()

    # Captures vs cost-aware PF if present, else vs reused PF
    oracle = ca_pf if ca_pf in net_rows else "perfect_foresight_daily"
    pf = net_rows[oracle]["final_cash_eur"]
    th = net_rows.get("threshold_arbitrage", {}).get("final_cash_eur")
    for r in net_rows.values():
        r["capture_vs_pf_pct"] = 100.0 * r["final_cash_eur"] / pf if pf else None
        r["vs_threshold_pct"] = 100.0 * r["final_cash_eur"] / th if th else None

    boot_thr = {}
    boot_ml = {}
    th_daily = net_daily.get("threshold_arbitrage")
    ml_daily = net_daily.get("ml_forecast_driven_lp")
    for name, daily in net_daily.items():
        if th_daily is not None and name != "threshold_arbitrage":
            boot_thr[name] = block_bootstrap_mean_diff_ci(daily, th_daily, block=7, n_boot=400, alpha=0.10, seed=0)
        if ml_daily is not None and name != "ml_forecast_driven_lp":
            boot_ml[name] = block_bootstrap_mean_diff_ci(daily, ml_daily, block=7, n_boot=400, alpha=0.10, seed=0)

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
        "reused_dumps": reused,
        "bootstrap_vs_threshold": boot_thr,
        "bootstrap_vs_nonreopt_ml": boot_ml,
        "cost_preset": preset,
        "cost_scenario_base": BASE.to_dict(),
        "cost_sources": COST_SOURCES if preset != "sourced" else sourced_preset_components()["catalog"],
        "sourced_preset": sourced_preset_components() if preset == "sourced" else None,
        "fee_retrieval_date": RETRIEVAL_DATE,
        "assumptions": [
            "Cost-aware LP puts fee+slippage+degradation in the objective (re-optimises)",
            "Baselines reuse prior gross (deg=0) dumps and the same accounting layer for the selected preset",
            "Tight Mondrian: hour-bucket × hourly residual-load tercile × 7d/60d hour volatility, with parent fallback",
            "Sourced fee is ECC DA clearing only; current EPEX trading fee is not in the public price list (lower bound)",
            "Degradation remains ASSUMED at 5 €/MWh in both presets",
            "Paper trading only",
        ],
        "attribution": "Energy-Charts / SMARD — CC BY 4.0",
        "paper_trading_only": True,
        "prior_reference": {
            "nonreopt_ml_net_eur": 57152.53,
            "threshold_net_eur": 31944.34,
            "mondrian_coverage_80": 0.7818991097922848,
        },
    }
    if preset == "sourced":
        dest = FC_RESULTS / "sourced_fees_backtest.json"
        json_bt = BT_RESULTS / "sourced_fees_backtest.json"
        csv_path = BT_RESULTS / "sourced_fees_backtest.csv"
    else:
        dest = FC_RESULTS / "cost_aware_tight_mondrian.json"
        json_bt = BT_RESULTS / "cost_aware_backtest.json"
        csv_path = BT_RESULTS / "cost_aware_backtest.csv"
    dest.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    json_bt.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    fields = [
        "strategy", "final_cash_eur", "capture_vs_pf_pct",
        "daily_pnl_p10", "daily_pnl_p50", "daily_pnl_p90",
        "cvar_5pct_loss_daily", "max_drawdown_eur", "cycles",
        "total_fees_eur", "total_slippage_eur", "total_degradation_eur", "throughput_mwh",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for name, r in net_rows.items():
            w.writerow({"strategy": name, **r})
    print(json.dumps({"strategies": net_rows, "boot_thr": boot_thr, "boot_ml": boot_ml, "cal": mae_tbl.get("calibration")}, indent=2, default=float))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
