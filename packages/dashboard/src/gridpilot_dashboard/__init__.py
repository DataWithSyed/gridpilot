"""GridPilot dashboard logic (testable; Streamlit UI is thin)."""
from gridpilot_dashboard.data import load_backtest_payload, strategies_frame
from gridpilot_dashboard.health import health_check

__all__ = ["load_backtest_payload", "strategies_frame", "health_check"]
__version__ = "0.1.0"
