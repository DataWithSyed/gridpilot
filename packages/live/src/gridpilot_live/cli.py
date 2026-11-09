"""CLI entry for the near-live paper pilot."""
from __future__ import annotations

import json

from gridpilot_live.pilot import LivePilotConfig, run_live_pilot


def main() -> None:
    summary = run_live_pilot(LivePilotConfig())
    print(summary.get("_markdown", json.dumps({k: v for k, v in summary.items() if k != "tomorrow"}, indent=2)))
    tm = summary["tomorrow"]
    print(
        f"\nTomorrow {tm['delivery_day']}: charge={tm['charge_hours']}h "
        f"discharge={tm['discharge_hours']}h hold={tm['hold_hours']}h "
        f"P50_mean={tm['forecast_p50_mean_eur_mwh']:.2f}"
    )
    print(f"Summary JSON → results/live/live_pilot_summary.json")


if __name__ == "__main__":
    main()
