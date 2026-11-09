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

from gridpilot_live.data import latest_published_price_day, load_or_extend_fundamentals


@dataclass
class LivePilotConfig:
    eval_days: int = 14
    lookback_days: int = 90
    refit_every_days: int = 7
    power_mw: float = 1.0
    energy_mwh: float = 2.0
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


def _settle_plan(
    plan: dict[pd.Timestamp, Any],
    prices: pd.Series,
    battery: BatteryConfig,
    state: BatteryState,
    *,
    dt_h: float = 1.0,
) -> tuple[BatteryState, float, list[dict]]:
    cash = 0.0
    rows = []
    for ts, px in prices.items():
        dec = plan.get(ts)
        if dec is None:
            c_mw = d_mw = 0.0
            note = "missing_plan"
        else:
            c_mw, d_mw, note = float(dec.charge_mw), float(dec.discharge_mw), dec.note
        # Clip to battery feasibility locally (same spirit as risk manager)
        c_mw = max(0.0, min(c_mw, battery.power_mw))
        d_mw = max(0.0, min(d_mw, battery.power_mw))
        if c_mw > 0 and d_mw > 0:
            d_mw = 0.0
        state, grid_in, grid_out = apply_dispatch(
            battery, state, charge_mw=c_mw, discharge_mw=d_mw, dt_h=dt_h
        )
        cash -= grid_in * float(px)
        cash += grid_out * float(px)
        cash -= (grid_in + grid_out) * battery.degradation_eur_per_mwh
        rows.append(
            {
                "ts": str(ts),
                "price": float(px),
                "charge_mw": c_mw,
                "discharge_mw": d_mw,
                "grid_in_mwh": grid_in,
                "grid_out_mwh": grid_out,
                "cash_step": -grid_in * float(px)
                + grid_out * float(px)
                - (grid_in + grid_out) * battery.degradation_eur_per_mwh,
                "soc": state.soc,
                "note": note,
            }
        )
    return state, cash, rows


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

    battery = BatteryConfig(power_mw=cfg.power_mw, energy_mwh=cfg.energy_mwh)
    state_ml = BatteryState.from_config(battery)
    state_pf = BatteryState.from_config(battery)
    state_th = BatteryState.from_config(battery)
    thr = ThresholdArbitrage()
    pf_strat = PerfectForesightDaily()

    ml_cash = 0.0
    pf_cash = 0.0
    th_cash = 0.0
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
        # History strictly before delivery day (ex-ante)
        hist = prices[prices.index.date < day.date()]
        if len(hist) < 24 * 21:
            continue
        day_prices = prices[prices.index.date == day.date()]
        if len(day_prices) < 20:
            continue
        # Align to 24h index when possible
        idx = day_prices.index
        pred = fc.predict_quantiles_for_day(hist, day)
        npred = naive.predict_day(panel_all, day)
        y = day_prices.to_numpy(float)
        # Map predictions to actual hours present
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

        # Ex-ante ML schedule: LP on forecast P50 path (no realised prices in path)
        fc_path = pd.Series(p50, index=idx, dtype=float)
        plan_ml = _solve_day_lp(fc_path, battery, state_ml, dt_h=1.0)
        state_ml, cash_d, fills = _settle_plan(plan_ml, day_prices, battery, state_ml)
        ml_cash += cash_d

        # Perfect foresight on realised DA (oracle once DA known)
        plan_pf = pf_strat._solve_day(day_prices, battery, state_pf)
        state_pf, cash_pf, _ = _settle_plan(plan_pf, day_prices, battery, state_pf)
        pf_cash += cash_pf

        # Threshold: hour-by-hour causal on history growing through the day
        cash_th_day = 0.0
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
            step = -gin * float(px) + gout * float(px) - (gin + gout) * battery.degradation_eur_per_mwh
            cash_th_day += step
        th_cash += cash_th_day

        day_row = {
            "day": str(day.date()),
            "ml_cash_eur": cash_d,
            "pf_cash_eur": cash_pf,
            "threshold_cash_eur": cash_th_day,
            "mae_ml": mae_ml[-1],
            "mae_naive": mae_nv[-1],
            "n_hours": int(len(day_prices)),
            "price_mean": float(day_prices.mean()),
        }
        day_rows.append(day_row)
        event_lines.append(json.dumps({"type": "day_summary", **day_row}))
        for fill in fills:
            event_lines.append(json.dumps({"type": "fill", "day": str(day.date()), **fill}))

    # Next-day schedule: first Berlin day AFTER the eval window that we can plan for.
    # If DA prices for that day are already in the feed, we still build the schedule
    # from the ex-ante forecast (and report that DA is published separately).
    tomorrow = (eval_end + pd.Timedelta(days=1)).tz_localize(None).normalize()
    hist_tm = prices[prices.index.date < tomorrow.date()]
    tm_idx = _berlin_day_index(tomorrow)
    tm_prices = prices[prices.index.date == tomorrow.date()]
    tm_da_published = len(tm_prices) >= 20
    tm_pred = fc.predict_quantiles_for_day(hist_tm, tomorrow)
    tm_path = pd.Series(tm_pred[0.50], index=tm_idx, dtype=float)
    # Use final ML SoC from eval window as starting SoC for tomorrow plan
    plan_tm = _solve_day_lp(tm_path, battery, state_ml, dt_h=1.0)
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
            }
        )
    )
    events_path.write_text("\n".join(event_lines) + ("\n" if event_lines else ""), encoding="utf-8")

    cal = evaluate_calibration(y_by_day, pred_by_day)
    capture = (100.0 * ml_cash / pf_cash) if pf_cash else None
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
            "starting_soc": float(state_ml.soc),
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
            "ml_exante_lp_cash_eur": float(ml_cash),
            "threshold_cash_eur": float(th_cash),
            "perfect_foresight_cash_eur": float(pf_cash),
            "ml_capture_vs_pf_pct": float(capture) if capture is not None else None,
            "daily": day_rows,
        },
        "validation_scope": {
            "is": [
                "Ex-ante day-ahead price forecast accuracy vs realised DE-LU DA prices",
                "P10–P90 interval coverage on those days",
                "Paper P&L of a day-locked schedule optimised on the P50 forecast, settled at realised DA",
                "Capture ratio vs perfect-foresight LP on the same realised DA curve",
            ],
            "is_not": [
                "Real order placement or exchange connectivity",
                "Intraday / imbalance / ancillary markets",
                "Bidding into SDAC before gate closure (DA prices for delivery day D are known after D-1 auction)",
                "Fees, slippage, or taxes (unless added elsewhere)",
            ],
        },
        "assumptions": [
            "ASSUMED 1 MW / 2 MWh BESS, η=0.95/0.95, SoC 5–95%, degradation 5 €/MWh-throughput",
            "ASSUMED ML lookback 90 d, refit every 7 d, CQR α=0.20",
            "Day-ahead fund forecasts ffilled ≤24 h when a tail day is missing",
            "Hourly means of native 15-min Energy-Charts MTU",
        ],
        "events_log": str(events_path),
        "extend_error": fund.attrs.get("extend_error"),
    }

    (summary_dir / "live_pilot_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    # Short markdown for humans
    acc = summary["accuracy"]
    pnl = summary["paper_pnl"]
    tm = summary["tomorrow"]
    md = f"""# Live paper pilot — {summary['eval_window']['start']} → {summary['eval_window']['end']}

Run at (Asia/Karachi): **{summary['run_at_asia_karachi']}**

Data: Energy-Charts DE-LU day-ahead + DE day-ahead load/solar/wind (CC BY 4.0).
Latest published DA price day: **{summary['latest_published_price_day']}**.

## Accuracy (ex-ante vs realised DA)

| Model | MAE €/MWh | RMSE €/MWh |
|---|---:|---:|
| ML + fundamentals + CQR | {acc['mae_ml_eur_mwh']:.2f} | {acc['rmse_ml_eur_mwh']:.2f} |
| Naive day-ahead | {acc['mae_naive_eur_mwh']:.2f} | {acc['rmse_naive_eur_mwh']:.2f} |

P10–P90 coverage: **{(acc['coverage_p10_p90'] or 0)*100:.1f}%** (nominal 80%), n={acc['n_days']} days.

## Paper P&L (1 MW / 2 MWh, day-locked ex-ante ML schedule)

| Strategy | Cash € | Capture of PF |
|---|---:|---:|
| ML ex-ante LP (P50 forecast) | {pnl['ml_exante_lp_cash_eur']:.2f} | {pnl['ml_capture_vs_pf_pct']:.1f}% |
| Threshold (causal) | {pnl['threshold_cash_eur']:.2f} | — |
| Perfect foresight (oracle) | {pnl['perfect_foresight_cash_eur']:.2f} | 100% |

## Tomorrow schedule ({tm['delivery_day']})

DA prices published: **{('yes' if tm['da_prices_published'] else 'no')}**. {('Ex-ante forecast schedule (DA already public).' if tm['da_prices_published'] else 'Forecast-only paper schedule.')} Mean P50 **{tm['forecast_p50_mean_eur_mwh']:.2f}** €/MWh
(P10 {tm['forecast_p10_mean_eur_mwh']:.2f} / P90 {tm['forecast_p90_mean_eur_mwh']:.2f}).
Charge hours: {tm['charge_hours']} · Discharge hours: {tm['discharge_hours']} · Hold: {tm['hold_hours']} · start SoC {tm['starting_soc']:.2f}.

## What this validates / does not

**Validates:** ex-ante DA forecast skill, interval coverage, paper capture of a forecast-based daily LP vs oracle on realised DA.

**Does not validate:** real orders, SDAC bidding before gate closure, intraday/imbalance/ancillary, fees/slippage.
"""
    (summary_dir / "LIVE_PILOT.md").write_text(md, encoding="utf-8")
    summary["_markdown"] = md
    return summary
