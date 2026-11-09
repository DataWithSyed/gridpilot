#!/usr/bin/env python3
"""Demo: bootstrap scenario cash distribution from a CSV price series or synthetic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from gridpilot_risk.bootstrap import scenario_revenue_distribution
from gridpilot_risk.var_cvar import distribution_summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--prices-csv", type=Path, default=None)
    p.add_argument("--n-scenarios", type=int, default=100)
    p.add_argument("--out", type=Path, default=Path("results/bootstrap_summary.json"))
    args = p.parse_args()
    if args.prices_csv and args.prices_csv.exists():
        s = pd.read_csv(args.prices_csv, parse_dates=[0], index_col=0).iloc[:, 0].astype(float)
    else:
        idx = pd.date_range("2026-08-01", periods=14 * 24, freq="h", tz="Europe/Berlin")
        hour = idx.hour
        s = pd.Series(120 + 50 * np.sin((hour - 6) / 24 * 2 * np.pi), index=idx)

    def pnl_fn(path: pd.Series) -> float:
        # Toy spread capture proxy (not a BESS sim): daily (max-min) sum * 0.5 MWh
        by = path.groupby(path.index.date)
        return float(sum((g.max() - g.min()) * 0.5 for _, g in by))

    dist = scenario_revenue_distribution(
        s, pnl_fn, n_scenarios=args.n_scenarios, block_days=7, rng=np.random.default_rng(42)
    )
    summary = distribution_summary(dist)
    summary["note"] = (
        "Toy spread proxy on bootstrapped paths — replace pnl_fn with PaperAgent cash for real runs."
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
