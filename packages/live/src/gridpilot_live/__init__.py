"""Near-live paper-trading pilot for GridPilot (never places real orders)."""

from gridpilot_live.pilot import LivePilotConfig, run_live_pilot

__all__ = ["LivePilotConfig", "run_live_pilot"]
__version__ = "0.1.0"
