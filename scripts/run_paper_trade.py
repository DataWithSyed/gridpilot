#!/usr/bin/env python3
"""Run paper-trading baselines on real Energy-Charts DE-LU day-ahead prices."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from gridpilot_core.agent import PaperAgent
from gridpilot_core.battery import BatteryConfig
from gridpilot_core.data_replay import load_or_fetch_prices
from gridpilot_core.risk import RiskLimits
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default="2026-08-01")
    p.add_argument("--end", default="2026-10-15")
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    prices = load_or_fetch_prices(args.start, args.end, refresh=args.refresh)
    if prices.empty:
        raise SystemExit("No prices returned")

    battery = BatteryConfig(
        energy_mwh=2.0,
        power_mw=1.0,
        eta_charge=0.95,
        eta_discharge=0.95,
        soc_min=0.05,
        soc_max=0.95,
        initial_soc=0.50,
        degradation_eur_per_mwh=5.0,
    )
    risk = RiskLimits(
        max_cycles_per_day=2.0,
        max_drawdown_eur=50_000.0,  # wide for baseline so we measure strategy, not stop
        enable_kill_switch=True,
    )

    strategies = [
        ThresholdArbitrage(lookback_hours=168, low_q=0.25, high_q=0.75, min_spread_eur=10.0),
        PerfectForesightDaily(),
    ]

    summaries = {
        "window": {"start": args.start, "end": args.end},
        "n_hours": int(len(prices)),
        "price_mean": float(prices.mean()),
        "price_min": float(prices.min()),
        "price_max": float(prices.max()),
        "negative_price_share": float((prices < 0).mean()),
        "attribution": (
            "Day-ahead prices: Energy-Charts.info (Fraunhofer ISE) / "
            "Bundesnetzagentur | SMARD.de, CC BY 4.0"
        ),
        "strategies": {},
    }

    for strat in strategies:
        agent = PaperAgent(battery, strat, risk)
        result = agent.run(prices)
        key = strat.name
        summaries["strategies"][key] = result.summary
        result.actions.to_csv(RESULTS / f"actions_{key}.csv", index=False)
        result.daily.to_csv(RESULTS / f"daily_pnl_{key}.csv", header=True)
        if not result.rolling_pct.empty:
            result.rolling_pct.to_csv(RESULTS / f"rolling_pnl_pct_{key}.csv")

    # Capture ratio: threshold final cash / perfect foresight final cash
    th = summaries["strategies"]["threshold_arbitrage"]["final_cash_eur"]
    pf = summaries["strategies"]["perfect_foresight_daily"]["final_cash_eur"]
    summaries["capture_ratio_threshold_vs_pf"] = (th / pf) if pf != 0 else None

    out = RESULTS / "summary.json"
    out.write_text(json.dumps(summaries, indent=2, default=str), encoding="utf-8")

    # Human-readable facts
    lines = [
        f"# Measured paper-trade results ({args.start} → {args.end})",
        "",
        f"- Hours: **{summaries['n_hours']}**",
        f"- DA price mean / min / max: **{summaries['price_mean']:.2f} / {summaries['price_min']:.2f} / {summaries['price_max']:.2f}** €/MWh",
        f"- Negative-price share: **{100*summaries['negative_price_share']:.2f} %**",
        f"- Attribution: {summaries['attribution']}",
        "",
    ]
    for name, s in summaries["strategies"].items():
        lines += [
            f"## {name}",
            f"- Final cash (after degradation): **{s['final_cash_eur']:.2f}** €",
            f"- Total equivalent full cycles: **{s['total_cycles']:.3f}**",
            f"- Daily PnL mean / P10 / P50 / P90: **{s['daily_pnl_mean_eur']:.2f} / {s['daily_pnl_p10_eur']:.2f} / {s['daily_pnl_p50_eur']:.2f} / {s['daily_pnl_p90_eur']:.2f}** €",
            f"- Kill switch: {s['killed']} ({s['kill_reason'] or '—'})",
            "",
        ]
    if summaries["capture_ratio_threshold_vs_pf"] is not None:
        lines.append(
            f"- Threshold capture of perfect-foresight cash: **{100*summaries['capture_ratio_threshold_vs_pf']:.1f} %**"
        )
    (RESULTS / "measured_facts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2, default=str))


if __name__ == "__main__":
    main()
