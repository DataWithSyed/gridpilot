#!/usr/bin/env python3
"""Backtest SDAC-style gate-closure bid curves vs the locked P50 schedule.

Paper trading only. Window: 2025-11-01 → 2026-10-30 (Europe/Berlin).
Default forecast is a causal 90-day hour-of-day climatology (P10/P50/P90)
so the year-long run stays memory-light. Pass --forecast ml to use the
same walk-forward quantile model as the production cost-aware agent
(heavier; processes one day at a time and garbage-collects).

Both policies see the same fan. Costs default to the sourced fee preset.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PKG / "packages" / "_srcpaths.py") if False else str(ROOT / "src"))

# Ensure monorepo packages import when run as a script.
for extra in (
    PKG / "packages" / "forecast" / "src",
    PKG / "packages" / "core" / "src",
    PKG / "packages" / "backtest" / "src",
    PKG / "packages" / "risk" / "src",
):
    s = str(extra)
    if s not in sys.path:
        sys.path.insert(0, s)

from gridpilot_backtest.costs import SOURCED_COSTS, get_cost_preset  # noqa: E402
from gridpilot_backtest.metrics import block_bootstrap_mean_diff_ci  # noqa: E402
from gridpilot_core.battery import BatteryConfig  # noqa: E402
from gridpilot_forecast.bid_curves import (  # noqa: E402
    evaluate_day,
    gate_closure_time,
    policy_summary,
    rolling_hod_quantiles,
)
from gridpilot_forecast.fundamentals import load_fundamentals  # noqa: E402

START = "2025-11-01"
END = "2026-10-30"
LOOKBACK_DAYS = 90


def _to_berlin(s: pd.Series) -> pd.Series:
    idx = pd.to_datetime(s.index, utc=True)
    s = s.copy()
    s.index = idx.tz_convert("Europe/Berlin")
    s = s[~s.index.duplicated(keep="first")].sort_index().astype(float)
    return s


def _days(prices: pd.Series, start: str, end: str) -> list[pd.Timestamp]:
    start_d = pd.Timestamp(start).date()
    end_d = pd.Timestamp(end).date()
    dates = pd.Index(prices.index.tz_convert("Europe/Berlin").date).unique()
    return [pd.Timestamp(d) for d in dates if start_d <= d <= end_d]


def _day_slice(prices: pd.Series, day: pd.Timestamp) -> pd.Series:
    d = day.date()
    mask = prices.index.tz_convert("Europe/Berlin").date == d
    return prices.loc[mask]


def _fan_climatology(history: pd.Series, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, pd.Series]:
    fans = rolling_hod_quantiles(history, index, lookback_days=LOOKBACK_DAYS)
    return fans[0.10], fans[0.50], fans[0.90]


def _fan_ml(wf, history: pd.Series, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, pd.Series]:
    fc = wf.forecast_day(history, index)
    p10 = fc.get(0.10, fc[min(fc)])
    p50 = fc.get(0.50, fc[min(fc, key=lambda k: abs(k - 0.5))])
    p90 = fc.get(0.90, fc[max(fc)])
    return p10.reindex(index), p50.reindex(index), p90.reindex(index)


def run(
    *,
    forecast: str = "climatology",
    costs_name: str = "sourced",
    start: str = START,
    end: str = END,
    out_dir: Path | None = None,
) -> dict:
    costs = get_cost_preset(costs_name)
    battery = BatteryConfig()  # 1 MW / 2 MWh, default SoC band
    cache = ROOT / "data" / "cache" / "de_lu_hourly.csv.gz"
    raw = load_fundamentals(cache)
    prices = _to_berlin(raw["price"])
    del raw
    gc.collect()

    days = _days(prices, start, end)
    if not days:
        raise RuntimeError(f"No prices in window {start} → {end}")

    wf = None
    if forecast == "ml":
        from gridpilot_forecast.forecaster import WalkForwardQuantileForecast

        wf = WalkForwardQuantileForecast(
            lookback_days=LOOKBACK_DAYS,
            refit_every_days=7,
            calibrate=True,
            calibrator_kind="mondrian",
            mondrian_mode="tight",
        )

    soc = {k: battery.initial_soc for k in ("schedule", "quantile_bid", "anchored_bid")}
    cash0 = {k: 0.0 for k in soc}
    daily = {k: [] for k in soc}
    thru = {k: 0.0 for k in soc}
    n_hours = 0
    t0 = time.time()

    for i, day in enumerate(days):
        px = _day_slice(prices, day)
        if px.empty:
            continue
        hist = prices[prices.index < px.index[0]]
        if forecast == "ml":
            p10, p50, p90 = _fan_ml(wf, hist, px.index)
        else:
            p10, p50, p90 = _fan_climatology(hist, px.index)
        ev = evaluate_day(
            px, p10, p50, p90, battery, costs,
            soc_schedule=soc["schedule"],
            soc_quantile=soc["quantile_bid"],
            soc_anchored=soc["anchored_bid"],
        )
        for key in ("schedule", "quantile_bid", "anchored_bid"):
            acts = ev[key]
            summary = policy_summary(acts, costs, initial_cash=cash0[key])
            pnl = float(summary["final_cash_eur"]) - cash0[key]
            cash0[key] = float(summary["final_cash_eur"])
            soc[key] = float(summary["end_soc"])
            thru[key] += float(summary.get("throughput_mwh_day") or 0.0)
            daily[key].append((day.date().isoformat(), pnl))
        n_hours += len(px)
        del ev, p10, p50, p90, px, hist
        if (i + 1) % 30 == 0:
            gc.collect()
            elapsed = time.time() - t0
            print(
                f"  {i+1}/{len(days)} days  "
                f"sched={cash0['schedule']:.1f}  "
                f"qbid={cash0['quantile_bid']:.1f}  "
                f"anc={cash0['anchored_bid']:.1f}  "
                f"{elapsed:.0f}s",
                flush=True,
            )

    def _series(pairs):
        return pd.Series({pd.Timestamp(d): v for d, v in pairs}, dtype=float)

    daily_s = {k: _series(v) for k, v in daily.items()}
    cis = {
        "quantile_bid_minus_schedule": block_bootstrap_mean_diff_ci(
            daily_s["quantile_bid"], daily_s["schedule"], block=7, n_boot=400, alpha=0.10, seed=0
        ),
        "anchored_bid_minus_schedule": block_bootstrap_mean_diff_ci(
            daily_s["anchored_bid"], daily_s["schedule"], block=7, n_boot=400, alpha=0.10, seed=0
        ),
        "quantile_bid_minus_anchored": block_bootstrap_mean_diff_ci(
            daily_s["quantile_bid"], daily_s["anchored_bid"], block=7, n_boot=400, alpha=0.10, seed=0
        ),
    }
    efc = 2.0  # BatteryConfig default energy_mwh
    result = {
        "paper_trading_only": True,
        "window": {"start": start, "end": end, "n_days": len(days), "n_hours": n_hours},
        "gate_closure": "12:00 Europe/Berlin on D-1",
        "forecast": forecast,
        "forecast_notes": (
            "Causal 90-day hour-of-day climatology (P10/P50/P90); same fan for all policies."
            if forecast == "climatology"
            else "Walk-forward quantile forecast (lookback 90 d, refit 7 d) plus tight Mondrian when available."
        ),
        "costs": costs.to_dict(),
        "battery": {"power_mw": battery.power_mw, "energy_mwh": battery.energy_mwh},
        "first_gate_closure": str(gate_closure_time(pd.Timestamp(start, tz="Europe/Berlin"))),
        "final_cash_eur": {k: float(cash0[k]) for k in cash0},
        "throughput_mwh": {k: float(thru[k]) for k in thru},
        "cycles": {k: float(thru[k] / (2.0 * efc)) for k in thru},
        "end_soc": {k: float(soc[k]) for k in soc},
        "bootstrap_daily_mean_diff_eur": {
            name: {kk: (None if isinstance(vv, float) and pd.isna(vv) else vv) for kk, vv in d.items()}
            for name, d in cis.items()
        },
        "marginal_accept_fraction_assumed": 0.5,
        "elapsed_s": time.time() - t0,
    }
    out_dir = Path(out_dir or (ROOT / "results"))
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "gate_closure_bidding.json"
    js.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    md = _render_md(result)
    (out_dir / "GATE_CLOSURE_BIDDING.md").write_text(md, encoding="utf-8")
    print(md)
    return result


def _render_md(r: dict) -> str:
    fc = r["final_cash_eur"]
    ci_q = r["bootstrap_daily_mean_diff_eur"]["quantile_bid_minus_schedule"]
    ci_a = r["bootstrap_daily_mean_diff_eur"]["anchored_bid_minus_schedule"]

    def _ci(c):
        if c.get("mean_diff") is None:
            return "n/a (too few days)"
        return (
            f"{c['mean_diff']:.2f} €/day  "
            f"90% CI [{c['ci_low']:.2f}, {c['ci_high']:.2f}]  "
            f"(n={c['n_days']}, block={c['block']}d, boot={c['n_boot']})"
        )

    q_vs = fc["quantile_bid"] - fc["schedule"]
    a_vs = fc["anchored_bid"] - fc["schedule"]
    helped_q = "improved" if q_vs > 0 else "did not improve"
    helped_a = "improved" if a_vs > 0 else "did not improve"
    return f"""# Gate-closure bid curves vs locked schedule (paper only)

Window: {r['window']['start']} → {r['window']['end']}  ({r['window']['n_days']} days, {r['window']['n_hours']} hours).
Gate closure: {r['gate_closure']}. First deadline: {r['first_gate_closure']}.
Forecast: **{r['forecast']}** — {r['forecast_notes']}
Costs: sourced preset (see `docs/fees.md`); marginal price-tie fraction ASSUMED {r['marginal_accept_fraction_assumed']}.

## Final net cash (EUR)

| Policy | Net EUR | Throughput MWh | Cycles |
| --- | ---: | ---: | ---: |
| Locked P50 cost-aware schedule | {fc['schedule']:.2f} | {r['throughput_mwh']['schedule']:.1f} | {r['cycles']['schedule']:.1f} |
| Quantile bid curves (P10/P50/P90) | {fc['quantile_bid']:.2f} | {r['throughput_mwh']['quantile_bid']:.1f} | {r['cycles']['quantile_bid']:.1f} |
| Schedule-anchored bid curves | {fc['anchored_bid']:.2f} | {r['throughput_mwh']['anchored_bid']:.1f} | {r['cycles']['anchored_bid']:.1f} |

- Quantile bids vs schedule: {q_vs:+.2f} EUR — **{helped_q}** on this window.
- Anchored bids vs schedule: {a_vs:+.2f} EUR — **{helped_a}** on this window.

## Incremental daily value (moving-block bootstrap)

- Quantile bids − schedule: {_ci(ci_q)}
- Anchored bids − schedule: {_ci(ci_a)}

A CI that contains 0 means the year-long difference is not distinguishable from noise at 90% under weekly blocks.

## What this does and does not show

- Same forecast fan for every policy; no lookahead into delivery-day prices.
- The locked schedule is a price-taking fill of the cost-aware LP on P50 (the current approach).
- Bid curves can refuse a fill when the realised clearing price misses the forecast; they can also under-fill a day the schedule would have planned better across hours (no explicit water-value in the standalone quantile curve).
- Climatology is not the production ML+CQR fan. Figures are not comparable to the published ML cost-aware 65,473 EUR path without a `--forecast ml` run.
- Paper trading only; no real orders.
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--forecast", choices=("climatology", "ml"), default="climatology")
    p.add_argument("--costs", default="sourced")
    p.add_argument("--start", default=START)
    p.add_argument("--end", default=END)
    args = p.parse_args(argv)
    run(forecast=args.forecast, costs_name=args.costs, start=args.start, end=args.end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
