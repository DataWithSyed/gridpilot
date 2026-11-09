"""Headless health check (no browser)."""
from __future__ import annotations

from gridpilot_dashboard.data import load_backtest_payload, strategies_frame


def health_check() -> dict:
    payload = load_backtest_payload()
    frame = strategies_frame(payload)
    ok = True
    reason = "ok"
    # Healthy even with empty results — package import + frame shape matter
    if "strategy" not in frame.columns:
        ok = False
        reason = "strategies_frame missing strategy column"
    return {
        "ok": ok,
        "reason": reason,
        "n_strategies": int(len(frame)),
        "has_results": bool(payload.get("strategies")),
        "paper_trading_only": True,
    }
