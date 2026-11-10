"""Ex-ante near-live paper pilot + forecast accuracy check."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gridpilot_core.battery import BatteryConfig, BatteryState, apply_dispatch
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage
from gridpilot_forecast.features import daily_panel, to_berlin
from gridpilot_forecast.forecaster import WalkForwardQuantileForecast, evaluate_calibration
from gridpilot_forecast.fundamentals import build_fundamentals_panels
from gridpilot_forecast.models import NaiveDayAhead, mae
from gridpilot_strategies.forecast_lp import _solve_day_lp
from gridpilot_backtest.costs import ExecutionCosts, ZERO_COSTS, apply_costs_to_actions
from gridpilot_forecast.cost_aware_lp import solve_day_lp_with_costs

from gridpilot_live.data import latest_published_price_day, load_or_extend_fundamentals


@dataclass
class LivePilotConfig:
    eval_days: int = 14
    lookback_days: int = 90
    refit_every_days: int = 7
    power_mw: float = 1.0
    energy_mwh: float = 2.0
    apply_costs: bool = True  # fee toggle: report gross + net; use cost-aware LP when True
    cost_aware_schedule: bool = True
    costs: ExecutionCosts | None = None
    base_cache: Path | None = None
    live_cache: Path | None = None
    events_path: Path | None = None
    summary_dir: Path | None = None


def _rmse(yhat: np.ndarray, y: np.ndarray) -> float:
    yhat = np.asarray(yhat, float)
    y = np.asarray(y, float)
    return float(np.sqrt(np.mean((yhat - y) ** 2)))


def _berlin_day_index(day: pd.Timestamp) -> pd.DatetimeIndex:
    day = pd.Timestamp(day).tz_localize(None).normalize()
    # 24 hourly stamps in Europe/Berlin
    start = pd.Timestamp(day).tz_localize("Europe/Berlin")
    return pd.date_range(start, periods=24, freq="h")


def _price_series_berlin(df: pd.DataFrame) -> pd.Series:
    s = to_berlin(df["price"].dropna().astype(float))
    s.name = "da_price_eur_mwh"
    return s


def _step_cash(grid_in: float, grid_out: float, price: float, costs: ExecutionCosts | None, deg_fallback: float) -> tuple[float, float]:
    """Return (gross_mid_cash, net_cash) for one interval."""
    gross = -grid_in * price + grid_out * price
    if costs is None:
        net = gross - (grid_in + grid_out) * deg_fallback
    else:
        buy = price + costs.slippage_eur_per_mwh
        sell = price - costs.slippage_eur_per_mwh
        thr = grid_in + grid_out
        net = -grid_in * buy + grid_out * sell - thr * (costs.fee_eur_per_mwh + costs.degradation_eur_per_mwh)
    return gross, net


def _settle_plan(
    plan: dict[pd.Timestamp, Any],
    prices: pd.Series,
    battery: BatteryConfig,
    state: BatteryState,
    *,
    dt_h: float = 1.0,
    costs: ExecutionCosts | None = None,
) -> tuple[BatteryState, float, list[dict], float]:
    """Settle a day plan. Returns (state, net_cash, rows, gross_cash).

    Gross is mid-price P&L with no fee/slippage/degradation. Net uses ``costs``
    if provided, otherwise only ``battery.degradation_eur_per_mwh`` (legacy).
    """
    net_cash = 0.0
    gross_cash = 0.0
    rows = []
    for ts, px in prices.items():
        dec = plan.get(ts)
        if dec is None:
            c_mw = d_mw = 0.0
            note = "missing_plan"
        else:
            c_mw, d_mw, note = float(dec.charge_mw), float(dec.discharge_mw), dec.note
        c_mw = max(0.0, min(c_mw, battery.power_mw))
        d_mw = max(0.0, min(d_mw, battery.power_mw))
        if c_mw > 0 and d_mw > 0:
            d_mw = 0.0
        state, grid_in, grid_out = apply_dispatch(
            battery, state, charge_mw=c_mw, discharge_mw=d_mw, dt_h=dt_h
        )
        gross, net = _step_cash(grid_in, grid_out, float(px), costs, battery.degradation_eur_per_mwh)
        gross_cash += gross
        net_cash += net
        rows.append(
            {
                "ts": str(ts),
                "price": float(px),
                "charge_mw": c_mw,
                "discharge_mw": d_mw,
                "grid_in_mwh": grid_in,
                "grid_out_mwh": grid_out,
                "cash_step": net,
                "cash_step_gross": gross,
                "cash_step_net": net,
                "soc": state.soc,
                "note": note,
            }
        )
    return state, net_cash, rows, gross_cash


def run_live_pilot(cfg: LivePilotConfig | None = None) -> dict[str, Any]:
    cfg = cfg or LivePilotConfig()
    root = Path(__file__).resolve().parents[4]  # umbrella repo
    pkg = Path(__file__).resolve().parents[2]
    base_cache = Path(
        cfg.base_cache
        or (root / "packages" / "forecast" / "data" / "cache" / "de_lu_hourly.csv.gz")
    )
    live_cache = Path(cfg.live_cache or (pkg / "data" / "cache" / "de_lu_hourly_live.csv.gz"))
    events_path = Path(cfg.events_path or (pkg / "results" / "events.jsonl"))
    summary_dir = Path(cfg.summary_dir or (root / "results" / "live"))
    events_path.parent.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    latest = latest_published_price_day()
    # Eval window: last cfg.eval_days published days inclusive
    eval_end = latest
    eval_start = eval_end - pd.Timedelta(days=cfg.eval_days - 1)
    lookback_start = (eval_start - pd.Timedelta(days=cfg.lookback_days + 14)).strftime("%Y-%m-%d")
    end_str = eval_end.strftime("%Y-%m-%d")

    fund = load_or_extend_fundamentals(
        base_cache=base_cache,
        out_cache=live_cache,
        end=end_str,
        lookback_start=lookback_start,
        refresh_tail=True,
    )
    prices = _price_series_berlin(fund)
    if prices.empty:
        raise RuntimeError("no prices available after fetch")

    # Confirm coverage
    panel_all = daily_panel(prices)
    start_d = pd.Timestamp(eval_start.tz_localize(None)).normalize()
    end_d = pd.Timestamp(eval_end.tz_localize(None)).normalize()
    eval_days = [
        d
        for d in panel_all.index
        if start_d <= pd.Timestamp(d).normalize() <= end_d
        and not panel_all.loc[d].isna().any()
    ]

    fund_panels = build_fundamentals_panels(fund.dropna(subset=["price"]))
    fc = WalkForwardQuantileForecast(
        lookback_days=cfg.lookback_days,
        refit_every_days=cfg.refit_every_days,
        use_fundamentals=True,
        calibrate=True,
        fundamentals=fund_panels,
    )
    naive = NaiveDayAhead()

    costs = cfg.costs or ExecutionCosts()
    # Degradation lives in ExecutionCosts when the fee toggle is on, so the
    # battery wear term is not applied twice inside apply_dispatch accounting.
    battery = BatteryConfig(
        power_mw=cfg.power_mw,
        energy_mwh=cfg.energy_mwh,
        degradation_eur_per_mwh=0.0,
    )
    state_ml_g = BatteryState.from_config(battery)
    state_ml_n = BatteryState.from_config(battery)
    state_pf_g = BatteryState.from_config(battery)
    state_pf_n = BatteryState.from_config(battery)
    state_th = BatteryState.from_config(battery)
    thr = ThresholdArbitrage()
    pf_strat = PerfectForesightDaily()
    use_cost_lp = bool(cfg.apply_costs and cfg.cost_aware_schedule)

    ml_gross = ml_net = 0.0
    pf_gross = pf_net = 0.0
    th_gross = th_net = 0.0
    mae_ml: list[float] = []
    mae_nv: list[float] = []
    rmse_ml: list[float] = []
    rmse_nv: list[float] = []
    y_by_day: dict = {}
    pred_by_day: dict = {}
    day_rows: list[dict] = []
    event_lines: list[str] = []

    for day in eval_days:
        day = pd.Timestamp(day).normalize()
        hist = prices[prices.index.date < day.date()]
        if len(hist) < 24 * 21:
            continue
        day_prices = prices[prices.index.date == day.date()]
        if len(day_prices) < 20:
            continue
        idx = day_prices.index
        pred = fc.predict_quantiles_for_day(hist, day)
        npred = naive.predict_day(panel_all, day)
        y = day_prices.to_numpy(float)
        hours = [ts.hour for ts in day_prices.index]
        p50 = np.array([pred[0.50][h] for h in hours], float)
        p10 = np.array([pred[0.10][h] for h in hours], float)
        p90 = np.array([pred[0.90][h] for h in hours], float)
        if npred is not None:
            nv = np.array([npred[h] for h in hours], float)
        else:
            nv = np.full(len(hours), float(hist.iloc[-1]))

        mae_ml.append(mae(p50, y))
        mae_nv.append(mae(nv, y))
        rmse_ml.append(_rmse(p50, y))
        rmse_nv.append(_rmse(nv, y))
        y_by_day[day] = y
        pred_by_day[day] = {0.10: p10, 0.50: p50, 0.90: p90}

        fc_path = pd.Series(p50, index=idx, dtype=float)
        plan_ml_g = _solve_day_lp(fc_path, battery, state_ml_g, dt_h=1.0)
        state_ml_g, _net_ig, fills_g, cash_ml_g = _settle_plan(
            plan_ml_g, day_prices, battery, state_ml_g, costs=ZERO_COSTS
        )
        if use_cost_lp:
            plan_ml_n = solve_day_lp_with_costs(fc_path, battery, state_ml_n, costs, dt_h=1.0)
        else:
            plan_ml_n = plan_ml_g
        settle_costs = costs if cfg.apply_costs else ZERO_COSTS
        state_ml_n, cash_ml_n, fills, cash_ml_n_gross = _settle_plan(
            plan_ml_n, day_prices, battery, state_ml_n, costs=settle_costs
        )
        ml_gross += cash_ml_g
        ml_net += cash_ml_n

        plan_pf_g = pf_strat._solve_day(day_prices, battery, state_pf_g)
        state_pf_g, _, _, cash_pf_g = _settle_plan(
            plan_pf_g, day_prices, battery, state_pf_g, costs=ZERO_COSTS
        )
        if use_cost_lp:
            plan_pf_n = solve_day_lp_with_costs(
                day_prices, battery, state_pf_n, costs, dt_h=1.0, note="cost_aware_pf"
            )
        else:
            plan_pf_n = plan_pf_g
        state_pf_n, cash_pf_n, _, _ = _settle_plan(
            plan_pf_n, day_prices, battery, state_pf_n, costs=settle_costs
        )
        pf_gross += cash_pf_g
        pf_net += cash_pf_n

        cash_th_g = cash_th_n = 0.0
        hist_th = hist.copy()
        for ts, px in day_prices.items():
            hist_th = pd.concat([hist_th, pd.Series({ts: float(px)})])
            dec = thr.decide(
                ts=ts,
                price=float(px),
                history=hist_th,
                battery=battery,
                state=state_th,
                remaining_day_prices=day_prices.loc[ts:],
            )
            state_th, gin, gout = apply_dispatch(
                battery, state_th, charge_mw=dec.charge_mw, discharge_mw=dec.discharge_mw, dt_h=1.0
            )
            g, n = _step_cash(gin, gout, float(px), settle_costs, 0.0)
            cash_th_g += -gin * float(px) + gout * float(px)
            cash_th_n += n
        th_gross += cash_th_g
        th_net += cash_th_n

        day_row = {
            "day": str(day.date()),
            "ml_gross_eur": cash_ml_g,
            "ml_net_eur": cash_ml_n,
            "pf_gross_eur": cash_pf_g,
            "pf_net_eur": cash_pf_n,
            "threshold_gross_eur": cash_th_g,
            "threshold_net_eur": cash_th_n,
            "ml_cash_eur": cash_ml_n if cfg.apply_costs else cash_ml_g,
            "pf_cash_eur": cash_pf_n if cfg.apply_costs else cash_pf_g,
            "threshold_cash_eur": cash_th_n if cfg.apply_costs else cash_th_g,
            "mae_ml": mae_ml[-1],
            "mae_naive": mae_nv[-1],
            "n_hours": int(len(day_prices)),
            "price_mean": float(day_prices.mean()),
        }
        day_rows.append(day_row)
        event_lines.append(json.dumps({"type": "day_summary", **day_row}))
        for fill in fills:
            event_lines.append(json.dumps({"type": "fill", "day": str(day.date()), **fill}))

    tomorrow = (eval_end + pd.Timedelta(days=1)).tz_localize(None).normalize()
    hist_tm = prices[prices.index.date < tomorrow.date()]
    tm_idx = _berlin_day_index(tomorrow)
    tm_prices = prices[prices.index.date == tomorrow.date()]
    tm_da_published = len(tm_prices) >= 20
    tm_pred = fc.predict_quantiles_for_day(hist_tm, tomorrow)
    tm_path = pd.Series(tm_pred[0.50], index=tm_idx, dtype=float)
    if use_cost_lp:
        plan_tm = solve_day_lp_with_costs(tm_path, battery, state_ml_n, costs, dt_h=1.0)
        start_soc = state_ml_n.soc
    else:
        plan_tm = _solve_day_lp(tm_path, battery, state_ml_g, dt_h=1.0)
        start_soc = state_ml_g.soc
    schedule = []
    for ts in tm_idx:
        dec = plan_tm.get(ts)
        schedule.append(
            {
                "ts": str(ts),
                "forecast_p10": float(tm_pred[0.10][ts.hour]),
                "forecast_p50": float(tm_pred[0.50][ts.hour]),
                "forecast_p90": float(tm_pred[0.90][ts.hour]),
                "charge_mw": float(dec.charge_mw) if dec else 0.0,
                "discharge_mw": float(dec.discharge_mw) if dec else 0.0,
                "note": dec.note if dec else "missing",
            }
        )
    event_lines.append(
        json.dumps(
            {
                "type": "tomorrow_schedule",
                "delivery_day": str(tomorrow.date()),
                "n_hours": len(schedule),
                "charge_hours": sum(1 for r in schedule if r["charge_mw"] > 1e-6),
                "discharge_hours": sum(1 for r in schedule if r["discharge_mw"] > 1e-6),
                "cost_aware": use_cost_lp,
            }
        )
    )
    events_path.write_text("\n".join(event_lines) + ("\n" if event_lines else ""), encoding="utf-8")

    cal = evaluate_calibration(y_by_day, pred_by_day)
    cap_g = (100.0 * ml_gross / pf_gross) if pf_gross else None
    cap_n = (100.0 * ml_net / pf_net) if pf_net else None
    headline_ml = ml_net if cfg.apply_costs else ml_gross
    headline_pf = pf_net if cfg.apply_costs else pf_gross
    headline_th = th_net if cfg.apply_costs else th_gross
    headline_cap = cap_n if cfg.apply_costs else cap_g
    summary: dict[str, Any] = {
        "run_at_asia_karachi": str(pd.Timestamp.now(tz="Asia/Karachi")),
        "data_source": "Energy-Charts DE-LU day-ahead prices + DE day-ahead load/solar/wind forecasts (CC BY 4.0)",
        "latest_published_price_day": str(eval_end.date()),
        "eval_window": {
            "start": str(eval_start.date()),
            "end": str(eval_end.date()),
            "n_days": len(day_rows),
            "n_hours": int(sum(r["n_hours"] for r in day_rows)),
        },
        "tomorrow": {
            "delivery_day": str(tomorrow.date()),
            "da_prices_published": bool(tm_da_published),
            "cost_aware_schedule": use_cost_lp,
            "note": (
                (
                    "DA prices for this delivery day are already published; the schedule "
                    "below was still built from the ex-ante P50 forecast (no look-ahead). "
                    "Gate-closure bidding is not simulated."
                )
                if tm_da_published
                else (
                    "Day-ahead prices for this delivery day were not published at run time; "
                    "schedule is forecast-only (paper). Gate-closure bidding is not simulated."
                )
            ),
            "forecast_p50_mean_eur_mwh": float(np.mean(tm_pred[0.50])),
            "forecast_p10_mean_eur_mwh": float(np.mean(tm_pred[0.10])),
            "forecast_p90_mean_eur_mwh": float(np.mean(tm_pred[0.90])),
            "charge_hours": sum(1 for r in schedule if r["charge_mw"] > 1e-6),
            "discharge_hours": sum(1 for r in schedule if r["discharge_mw"] > 1e-6),
            "hold_hours": sum(
                1 for r in schedule if r["charge_mw"] <= 1e-6 and r["discharge_mw"] <= 1e-6
            ),
            "starting_soc": float(start_soc),
            "schedule": schedule,
        },
        "accuracy": {
            "mae_ml_eur_mwh": float(np.mean(mae_ml)) if mae_ml else None,
            "mae_naive_eur_mwh": float(np.mean(mae_nv)) if mae_nv else None,
            "rmse_ml_eur_mwh": float(np.mean(rmse_ml)) if rmse_ml else None,
            "rmse_naive_eur_mwh": float(np.mean(rmse_nv)) if rmse_nv else None,
            "n_days": len(mae_ml),
            "coverage_p10_p90": cal.get("coverage_80"),
            "reliability": cal.get("reliability"),
            "nominal_coverage": 0.80,
        },
        "paper_pnl": {
            "battery": f"{cfg.power_mw:g} MW / {cfg.energy_mwh:g} MWh",
            "apply_costs": bool(cfg.apply_costs),
            "cost_aware_schedule": use_cost_lp,
            "costs": costs.to_dict() if cfg.apply_costs else None,
            "ml_exante_lp_cash_eur": float(headline_ml),
            "threshold_cash_eur": float(headline_th),
            "perfect_foresight_cash_eur": float(headline_pf),
            "ml_capture_vs_pf_pct": float(headline_cap) if headline_cap is not None else None,
            "gross": {
                "ml_exante_lp_cash_eur": float(ml_gross),
                "threshold_cash_eur": float(th_gross),
                "perfect_foresight_cash_eur": float(pf_gross),
                "ml_capture_vs_pf_pct": float(cap_g) if cap_g is not None else None,
            },
            "net": {
                "ml_exante_lp_cash_eur": float(ml_net),
                "threshold_cash_eur": float(th_net),
                "perfect_foresight_cash_eur": float(pf_net),
                "ml_capture_vs_pf_pct": float(cap_n) if cap_n is not None else None,
            },
            "daily": day_rows,
        },
        "validation_scope": {
            "is": [
                "Ex-ante day-ahead price forecast accuracy vs realised DE-LU DA prices",
                "P10–P90 interval coverage on those days",
                "Paper P&L of a day-locked schedule optimised on the P50 forecast, settled at realised DA",
                "Capture ratio vs perfect-foresight LP on the same realised DA curve",
                "Gross vs net-of-ASSUMED-cost paper P&L (fee toggle)",
            ],
            "is_not": [
                "Real order placement or exchange connectivity",
                "Intraday / imbalance / ancillary markets",
                "Bidding into SDAC before gate closure (DA prices for delivery day D are known after D-1 auction)",
            ],
        },
        "assumptions": [
            "ASSUMED 1 MW / 2 MWh BESS, η=0.95/0.95, SoC 5–95%",
            "ASSUMED ML lookback 90 d, refit every 7 d, CQR α=0.20",
            "Base costs ASSUMED: fee 0.05 €/MWh, slippage 0.50 €/MWh, degradation 5 €/MWh" if cfg.apply_costs else "Fee toggle off: gross mid-price P&L only",
            "Day-ahead fund forecasts ffilled ≤24 h when a tail day is missing",
            "Hourly means of native 15-min Energy-Charts MTU",
        ],
        "events_log": str(events_path),
        "extend_error": fund.attrs.get("extend_error"),
    }

    (summary_dir / "live_pilot_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    acc = summary["accuracy"]
    pnl = summary["paper_pnl"]
    tm = summary["tomorrow"]
    md = f"""# Live paper pilot — {summary['eval_window']['start']} → {summary['eval_window']['end']}

Run at (Asia/Karachi): **{summary['run_at_asia_karachi']}**

Data: Energy-Charts DE-LU day-ahead + DE day-ahead load/solar/wind (CC BY 4.0).
Latest published DA price day: **{summary['latest_published_price_day']}**.
Fee toggle: **{'on' if cfg.apply_costs else 'off'}** (cost-aware LP: {use_cost_lp}).

## Accuracy (ex-ante vs realised DA)

| Model | MAE €/MWh | RMSE €/MWh |
|---|---:|---:|
| ML + fundamentals + CQR | {acc['mae_ml_eur_mwh']:.2f} | {acc['rmse_ml_eur_mwh']:.2f} |
| Naive day-ahead | {acc['mae_naive_eur_mwh']:.2f} | {acc['rmse_naive_eur_mwh']:.2f} |

P10–P90 coverage: **{(acc['coverage_p10_p90'] or 0)*100:.1f}%** (nominal 80%), n={acc['n_days']} days.

## Paper P&L (1 MW / 2 MWh, day-locked ex-ante ML schedule)

| Strategy | Gross € | Net of ASSUMED costs € | Capture of PF (gross / net) |
|---|---:|---:|---|
| ML ex-ante LP (P50; net uses cost-aware LP when toggle on) | {pnl['gross']['ml_exante_lp_cash_eur']:.2f} | {pnl['net']['ml_exante_lp_cash_eur']:.2f} | {pnl['gross']['ml_capture_vs_pf_pct']:.1f}% / {pnl['net']['ml_capture_vs_pf_pct']:.1f}% |
| Threshold (causal) | {pnl['gross']['threshold_cash_eur']:.2f} | {pnl['net']['threshold_cash_eur']:.2f} | — |
| Perfect foresight (oracle) | {pnl['gross']['perfect_foresight_cash_eur']:.2f} | {pnl['net']['perfect_foresight_cash_eur']:.2f} | 100% |

Gross is mid-price P&L with no fee/slippage/degradation. Net uses ASSUMED fee 0.05, slippage 0.50, degradation 5 €/MWh. Previous pilots included core default degradation (5 €/MWh) but not fee/slippage.

## Tomorrow schedule ({tm['delivery_day']})

DA prices published: **{('yes' if tm['da_prices_published'] else 'no')}**. {('Ex-ante forecast schedule (DA already public).' if tm['da_prices_published'] else 'Forecast-only paper schedule.')} Mean P50 **{tm['forecast_p50_mean_eur_mwh']:.2f}** €/MWh
(P10 {tm['forecast_p10_mean_eur_mwh']:.2f} / P90 {tm['forecast_p90_mean_eur_mwh']:.2f}).
Charge hours: {tm['charge_hours']} · Discharge hours: {tm['discharge_hours']} · Hold: {tm['hold_hours']} · start SoC {tm['starting_soc']:.2f}.

## What this validates / does not

**Validates:** ex-ante DA forecast skill, interval coverage, paper capture of a forecast-based daily LP vs oracle on realised DA, gross vs net-of-ASSUMED-cost paper P&L.

**Does not validate:** real orders, SDAC bidding before gate closure, intraday/imbalance/ancillary.
"""
    (summary_dir / "LIVE_PILOT.md").write_text(md, encoding="utf-8")
    summary["_markdown"] = md
    return summary
