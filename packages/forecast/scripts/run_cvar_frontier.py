#!/usr/bin/env python3
"""Walk-forward cost-aware CVaR LP frontier under the sourced fee preset (paper only).

Window: 2025-11-01 → 2026-10-30. Scenarios: last 60 causal daily price paths.
Sweep lambda, report out-of-sample mean daily cash vs historical CVaR5% of loss.
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
for extra in (
    PKG / "packages" / "forecast" / "src",
    PKG / "packages" / "core" / "src",
    PKG / "packages" / "backtest" / "src",
):
    s = str(extra)
    if s not in sys.path:
        sys.path.insert(0, s)

from gridpilot_backtest.costs import get_cost_preset  # noqa: E402
from gridpilot_backtest.metrics import historical_cvar  # noqa: E402
from gridpilot_core.battery import BatteryConfig, BatteryState  # noqa: E402
from gridpilot_forecast.bid_curves import policy_summary, settle_locked_schedule  # noqa: E402
from gridpilot_forecast.cvar_lp import (  # noqa: E402
    DEFAULT_ALPHA,
    DEFAULT_LAMBDA_GRID,
    DEFAULT_N_SCENARIOS,
    historical_day_scenarios,
    solve_day_lp_cvar,
)
from gridpilot_forecast.fundamentals import load_fundamentals  # noqa: E402

START = "2025-11-01"
END = "2026-10-30"


def _to_berlin(s: pd.Series) -> pd.Series:
    s = s.copy()
    s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Berlin")
    return s[~s.index.duplicated(keep="first")].sort_index().astype(float)


def _days(prices, start, end):
    start_d = pd.Timestamp(start).date()
    end_d = pd.Timestamp(end).date()
    dates = pd.Index(prices.index.tz_convert("Europe/Berlin").date).unique()
    return [pd.Timestamp(d) for d in dates if start_d <= d <= end_d]


def _day_slice(prices, day):
    d = day.date()
    return prices.loc[prices.index.tz_convert("Europe/Berlin").date == d]


def run(*, start=START, end=END, costs_name="sourced", lambdas=DEFAULT_LAMBDA_GRID) -> dict:
    costs = get_cost_preset(costs_name)
    battery = BatteryConfig()
    prices = _to_berlin(load_fundamentals(ROOT / "data" / "cache" / "de_lu_hourly.csv.gz")["price"])
    days = _days(prices, start, end)
    lambdas = tuple(float(x) for x in lambdas)
    soc = {lam: battery.initial_soc for lam in lambdas}
    cash = {lam: 0.0 for lam in lambdas}
    daily = {lam: [] for lam in lambdas}
    t0 = time.time()
    n_hours = 0
    for i, day in enumerate(days):
        px = _day_slice(prices, day)
        if px.empty:
            continue
        hist = prices[prices.index < px.index[0]]
        scenarios = historical_day_scenarios(hist, px.index, n_days=DEFAULT_N_SCENARIOS)
        if not scenarios:
            scenarios = [pd.Series(float(hist.iloc[-1]) if len(hist) else 0.0, index=px.index)]
        for lam in lambdas:
            plan = solve_day_lp_cvar(
                scenarios, battery, BatteryState(soc=soc[lam]), costs, lam=lam, alpha=DEFAULT_ALPHA
            )
            acts = settle_locked_schedule(plan, px, battery, soc[lam], note=f"cvar_l{lam}")
            summ = policy_summary(acts, costs, initial_cash=cash[lam])
            pnl = float(summ["final_cash_eur"]) - cash[lam]
            cash[lam] = float(summ["final_cash_eur"])
            soc[lam] = float(summ["end_soc"])
            daily[lam].append((day.date().isoformat(), pnl))
        n_hours += len(px)
        if (i + 1) % 30 == 0:
            gc.collect()
            bits = "  ".join(f"l{lam}={cash[lam]:.0f}" for lam in lambdas)
            print(f"  {i+1}/{len(days)}  {bits}  {time.time()-t0:.0f}s", flush=True)
        del px, hist, scenarios

    frontier = []
    for lam in lambdas:
        s = pd.Series({pd.Timestamp(d): v for d, v in daily[lam]}, dtype=float)
        # historical_cvar is CVaR of losses: positive = worse
        cvar = float(historical_cvar(s, alpha=DEFAULT_ALPHA))
        frontier.append({
            "lambda": lam,
            "final_cash_eur": float(cash[lam]),
            "mean_daily_eur": float(s.mean()) if len(s) else None,
            "cvar5_loss_eur": cvar,
            "n_days": int(len(s)),
        })
    result = {
        "paper_trading_only": True,
        "window": {"start": start, "end": end, "n_days": len(days), "n_hours": n_hours},
        "costs": costs.to_dict(),
        "alpha": DEFAULT_ALPHA,
        "n_scenarios": DEFAULT_N_SCENARIOS,
        "scenario_source": "causal last-60 Berlin daily price paths, hour-aligned",
        "frontier": frontier,
        "elapsed_s": time.time() - t0,
    }
    out = ROOT / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "cvar_frontier.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    (out / "CVAR_FRONTIER.md").write_text(_md(result))
    print(_md(result))
    return result


def _md(r: dict) -> str:
    rows = []
    for p in r["frontier"]:
        rows.append(
            f"| {p['lambda']:g} | {p['final_cash_eur']:.2f} | {p['mean_daily_eur']:.2f} | {p['cvar5_loss_eur']:.2f} |"
        )
    # identify knee: max cash, min cvar
    pts = r["frontier"]
    best_ret = max(pts, key=lambda p: p["final_cash_eur"])
    best_cvar = min(pts, key=lambda p: p["cvar5_loss_eur"])
    return f"""# Cost-aware CVaR frontier (paper only)

Window: {r['window']['start']} → {r['window']['end']} ({r['window']['n_days']} days, {r['window']['n_hours']} hours).
Costs: sourced preset. Scenarios: {r['scenario_source']}. CVaR level α={r['alpha']:.0%}.
Objective: maximise E[cash] − λ CVaR_α(loss). Out-of-sample figures below are from the locked plan settled at realised DA.

| λ | Net EUR | Mean €/day | OOS CVaR₅% loss € |
| ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

Highest net cash: λ={best_ret['lambda']:g} at {best_ret['final_cash_eur']:.2f} EUR (CVaR₅% {best_ret['cvar5_loss_eur']:.2f}).
Lowest OOS CVaR₅% loss: λ={best_cvar['lambda']:g} at {best_cvar['cvar5_loss_eur']:.2f} EUR (cash {best_cvar['final_cash_eur']:.2f}).

These points are a discrete efficient-frontier sample, not a continuous curve. Higher λ is not guaranteed to improve *out-of-sample* CVaR. Paper trading only.
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default=START)
    p.add_argument("--end", default=END)
    p.add_argument("--costs", default="sourced")
    args = p.parse_args(argv)
    run(start=args.start, end=args.end, costs_name=args.costs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
