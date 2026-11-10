#!/usr/bin/env python3
"""Fetch a short DE-LU sample via EnergyChartsAdapter and print summary stats."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gridpilot_data.adapters import EnergyChartsAdapter


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2026-08-01")
    p.add_argument("--end", default="2026-10-15")
    p.add_argument("--cache", type=Path, default=Path("data/cache"))
    p.add_argument("--out", type=Path, default=Path("results/sample_summary.json"))
    args = p.parse_args()
    ad = EnergyChartsAdapter(cache_dir=args.cache)
    prices = ad.fetch_day_ahead_prices(args.start, args.end)
    summary = {
        "start": args.start,
        "end": args.end,
        "n_hours": int(len(prices)),
        "mean_eur_mwh": float(prices.mean()) if len(prices) else None,
        "min_eur_mwh": float(prices.min()) if len(prices) else None,
        "max_eur_mwh": float(prices.max()) if len(prices) else None,
        "negative_share": float((prices < 0).mean()) if len(prices) else None,
        "attribution": "Energy-Charts / SMARD — CC BY 4.0",
        "note": "15-min MTU resampled to hourly means when to_hourly=True (default).",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
