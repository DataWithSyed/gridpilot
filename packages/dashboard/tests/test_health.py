"""Dashboard logic tests (no Streamlit required)."""
from __future__ import annotations

import json
from pathlib import Path

from gridpilot_dashboard.data import strategies_frame
from gridpilot_dashboard.health import health_check


def test_health_ok():
    h = health_check()
    assert h["ok"] is True
    assert h["paper_trading_only"] is True


def test_strategies_frame(tmp_path: Path):
    payload = {
        "strategies": {
            "threshold_arbitrage": {"final_cash_eur": 100.0, "capture_vs_pf_pct": 40.0},
            "perfect_foresight_daily": {"final_cash_eur": 250.0, "capture_vs_pf_pct": 100.0},
        }
    }
    df = strategies_frame(payload)
    assert len(df) == 2
    assert set(df["strategy"]) == {"threshold_arbitrage", "perfect_foresight_daily"}
