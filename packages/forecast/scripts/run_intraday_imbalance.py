#!/usr/bin/env python3
"""Backtest post-DA ID re-optimisation and a labelled reBAP proxy (paper only).

Energy-Charts has no public ID/ID-index series (verified 2026-11-10).
ID mid and reBAP default to the realised DA price (PROXY_ID_EQ_DA /
PROXY_REBAP_EQ_DA). Window: 2025-11-01 → 2026-10-30, sourced fees.
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
from gridpilot_backtest.metrics import block_bootstrap_mean_diff_ci  # noqa: E402
from gridpilot_core.battery import BatteryConfig, BatteryState  # noqa: E402
from gridpilot_forecast.bid_curves import (  # noqa: E402
    policy_summary,
    rolling_hod_quantiles,
    settle_locked_schedule,
)
from gridpilot_forecast.cost_aware_lp import solve_day_lp_with_costs  # noqa: E402
from gridpilot_forecast.fundamentals import load_fundamentals  # noqa: E402
from gridpilot_forecast.intraday import (  # noqa: E402
    ID_PRICE_SOURCE_NOTES,
    REBAP_SOURCE_NOTES,
    IntradayLayerConfig,
    reoptimize_after_da,
)

START = "2025-11-01"
END = "2026-10-30"
LOOKBACK_DAYS = 90


def _to_berlin(s: pd.Series) -> pd.Series:
    s = s.copy()
    s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Berlin")
    return s[~s.index.duplicated(keep="first")].sort_index().astype(float)


def _days(prices: pd.Series, start: str, end: str) -> list[pd.Timestamp]:
    start_d = pd.Timestamp(start).date()
    end_d = pd.Timestamp(end).date()
    dates = pd.Index(prices.index.tz_convert("Europe/Berlin").date).unique()
    return [pd.Timestamp(d) for d in dates if start_d <= d <= end_d]


def _day_slice(prices: pd.Series, day: pd.Timestamp) -> pd.Series:
    d = day.date()
    return prices.loc[prices.index.tz_convert("Europe/Berlin").date == d]


def run(*, start: str = START, end: str = END, costs_name: str = "sourced") -> dict:
    da_costs = get_cost_preset(costs_name)
    battery = BatteryConfig()
    cache = ROOT / "data" / "cache" / "de_lu_hourly.csv.gz"
    prices = _to_berlin(load_fundamentals(cache)["price"])
    days = _days(prices, start, end)
    cfg_full = IntradayLayerConfig(da_costs=da_costs, unfilled_frac=0.0)
    cfg_partial = IntradayLayerConfig(da_costs=da_costs, unfilled_frac=0.20)  # ASSUMED
    soc = {"da": battery.initial_soc, "id_full": battery.initial_soc, "id_partial": battery.initial_soc}
    cash = {k: 0.0 for k in soc}
    daily = {k: [] for k in soc}
    id_thr = {"id_full": 0.0, "id_partial": 0.0}
    imb_abs = {"id_full": 0.0, "id_partial": 0.0}
    n_hours = 0
    t0 = time.time()
    for i, day in enumerate(days):
        px = _day_slice(prices, day)
        if px.empty:
            continue
        hist = prices[prices.index < px.index[0]]
        fans = rolling_hod_quantiles(hist, px.index, lookback_days=LOOKBACK_DAYS)
        p50 = fans[0.50]
        da_plan = solve_day_lp_with_costs(
            p50, battery, BatteryState(soc=soc["da"]), da_costs, note="da_locked"
        )
        da_acts = settle_locked_schedule(da_plan, px, battery, soc["da"])
        da_sum = policy_summary(da_acts, da_costs, initial_cash=cash["da"])
        pnl_da = float(da_sum["final_cash_eur"]) - cash["da"]
        cash["da"] = float(da_sum["final_cash_eur"])
        soc["da"] = float(da_sum["end_soc"])
        daily["da"].append((day.date().isoformat(), pnl_da))

        for key, cfg in (("id_full", cfg_full), ("id_partial", cfg_partial)):
            out = reoptimize_after_da(da_plan, px, battery, soc[key], cfg)
            pnl = float(out["final_cash_eur"])
            # out cash is the day's cash starting at 0; add to running
            cash[key] += pnl
            soc[key] = float(out["end_soc"])
            daily[key].append((day.date().isoformat(), pnl))
            id_thr[key] += float(out["id_throughput_mwh"])
            imb_abs[key] += float(out["imb_abs_mwh"])
        n_hours += len(px)
        del px, hist, fans, p50, da_plan, da_acts
        if (i + 1) % 30 == 0:
            gc.collect()
            print(
                f"  {i+1}/{len(days)}  da={cash['da']:.1f}  "
                f"id0={cash['id_full']:.1f}  id20={cash['id_partial']:.1f}  "
                f"{time.time()-t0:.0f}s",
                flush=True,
            )

    def _s(pairs):
        return pd.Series({pd.Timestamp(d): v for d, v in pairs}, dtype=float)

    daily_s = {k: _s(v) for k, v in daily.items()}
    cis = {
        "id_full_minus_da": block_bootstrap_mean_diff_ci(
            daily_s["id_full"], daily_s["da"], block=7, n_boot=400, alpha=0.10, seed=0
        ),
        "id_partial_minus_da": block_bootstrap_mean_diff_ci(
            daily_s["id_partial"], daily_s["da"], block=7, n_boot=400, alpha=0.10, seed=0
        ),
        "id_full_minus_partial": block_bootstrap_mean_diff_ci(
            daily_s["id_full"], daily_s["id_partial"], block=7, n_boot=400, alpha=0.10, seed=0
        ),
    }
    result = {
        "paper_trading_only": True,
        "window": {"start": start, "end": end, "n_days": len(days), "n_hours": n_hours},
        "forecast": "climatology_p50_for_da_lock",
        "id_price_source": "proxy_id_eq_da",
        "rebap_source": "proxy_rebap_eq_da",
        "id_price_notes": ID_PRICE_SOURCE_NOTES,
        "rebap_notes": REBAP_SOURCE_NOTES,
        "unfilled_frac_partial_assumed": 0.20,
        "costs_da": da_costs.to_dict(),
        "id_fee_eur_per_mwh": cfg_full.id_costs.fee_eur_per_mwh,
        "final_cash_eur": {k: float(cash[k]) for k in cash},
        "id_throughput_mwh": id_thr,
        "imb_abs_mwh": imb_abs,
        "bootstrap_daily_mean_diff_eur": {
            name: {kk: (None if isinstance(vv, float) and pd.isna(vv) else vv) for kk, vv in d.items()}
            for name, d in cis.items()
        },
        "elapsed_s": time.time() - t0,
    }
    out_dir = ROOT / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "intraday_imbalance.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    md = _md(result)
    (out_dir / "INTRADAY_IMBALANCE.md").write_text(md)
    print(md)
    return result


def _md(r: dict) -> str:
    fc = r["final_cash_eur"]
    def ci(c):
        if c.get("mean_diff") is None:
            return "n/a"
        return f"{c['mean_diff']:.2f} €/day  90% CI [{c['ci_low']:.2f}, {c['ci_high']:.2f}] (n={c['n_days']})"
    d_full = fc["id_full"] - fc["da"]
    d_part = fc["id_partial"] - fc["da"]
    h_full = "improved" if d_full > 0 else "did not improve"
    h_part = "improved" if d_part > 0 else "did not improve"
    c1 = r["bootstrap_daily_mean_diff_eur"]["id_full_minus_da"]
    c2 = r["bootstrap_daily_mean_diff_eur"]["id_partial_minus_da"]
    return f"""# Post-DA re-optimisation and imbalance (paper only)

Window: {r['window']['start']} → {r['window']['end']} ({r['window']['n_days']} days, {r['window']['n_hours']} hours).
DA lock: causal 90-day hour-of-day P50 + cost-aware LP, sourced DA fees.
ID prices: **{r['id_price_source']}**. {r['id_price_notes']}
reBAP: **{r['rebap_source']}**. {r['rebap_notes']}
Partial-close unfilled fraction: ASSUMED {r['unfilled_frac_partial_assumed']:.0%}. ECC ID clearing {r['id_fee_eur_per_mwh']} €/MWh on filled ID volume.

## Final net cash (EUR)

| Policy | Net EUR | ID throughput MWh | |imbalance| MWh |
| --- | ---: | ---: | ---: |
| Locked DA schedule (no ID) | {fc['da']:.2f} | — | — |
| Post-DA re-opt, full ID close (unfilled 0) | {fc['id_full']:.2f} | {r['id_throughput_mwh']['id_full']:.1f} | {r['imb_abs_mwh']['id_full']:.1f} |
| Post-DA re-opt, ASSUMED 20% unfilled at reBAP proxy | {fc['id_partial']:.2f} | {r['id_throughput_mwh']['id_partial']:.1f} | {r['imb_abs_mwh']['id_partial']:.1f} |

- Full ID close vs locked DA: {d_full:+.2f} EUR — **{h_full}**.
- 20% unfilled vs locked DA: {d_part:+.2f} EUR — **{h_part}**.

## Incremental daily value (moving-block bootstrap, 7 d, 400 draws, 90% CI)

- Full ID close − locked DA: {ci(c1)}
- 20% unfilled − locked DA: {ci(c2)}

## What this does and does not show

- This is **not** a real ID-index or official reBAP backtest. Both legs are proxied by realised DA because those series were not publicly fetchable.
- Under PROXY_ID_EQ_DA, the lift is the value of reshaping after DA prices are published, minus ECC ID fees, with no ID–DA spread.
- PROXY_REBAP_EQ_DA ignores scarcity adders; the 20% unfilled case is an ASSUMED residual, not a measured fill rate.
- Paper trading only; no real orders.
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
