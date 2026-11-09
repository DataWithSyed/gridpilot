#!/usr/bin/env python3
"""Fetch DE-LU prices + day-ahead load/solar/wind forecasts (Energy-Charts CC BY 4.0)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gridpilot_forecast.fundamentals import DEFAULT_CACHE, fetch_fundamentals


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-11-01")
    ap.add_argument("--end", default="2026-10-30")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    df = fetch_fundamentals(args.start, args.end, cache_dir=args.cache, refresh=args.refresh)
    print(f"rows={len(df)} cols={list(df.columns)} range={df.index.min()}→{df.index.max()}")
    print(f"cache={args.cache}")


if __name__ == "__main__":
    main()
