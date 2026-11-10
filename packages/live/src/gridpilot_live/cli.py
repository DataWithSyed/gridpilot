"""CLI entry for the near-live paper pilot."""
from __future__ import annotations

import argparse
import json

from gridpilot_backtest.costs import get_cost_preset
from gridpilot_live.pilot import LivePilotConfig, run_live_pilot


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Near-live paper pilot (no real orders).")
    parser.add_argument(
        "--costs",
        default="sourced",
        choices=("sourced", "assumed", "base", "zero"),
        help="Cost preset used when the fee toggle is on (default: sourced).",
    )
    parser.add_argument("--no-costs", action="store_true", help="Fee toggle off: gross mid-price only.")
    args = parser.parse_args(argv)
    cfg = LivePilotConfig(
        apply_costs=not args.no_costs,
        costs=get_cost_preset(args.costs),
    )
    summary = run_live_pilot(cfg)
    print(summary.get("_markdown", json.dumps({k: v for k, v in summary.items() if k != "tomorrow"}, indent=2)))
    tm = summary["tomorrow"]
    print(
        f"\nTomorrow {tm['delivery_day']}: charge={tm['charge_hours']}h "
        f"discharge={tm['discharge_hours']}h hold={tm['hold_hours']}h "
        f"P50_mean={tm['forecast_p50_mean_eur_mwh']:.2f}"
    )
    print("Summary JSON → results/live/live_pilot_summary.json")


if __name__ == "__main__":
    main()
