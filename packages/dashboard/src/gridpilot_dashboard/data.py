"""Load backtest / forecast result JSON for the dashboard."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULT_CANDIDATES = [
    Path(__file__).resolve().parents[4] / "packages" / "backtest" / "results" / "backtest.json",
    Path(__file__).resolve().parents[4] / "packages" / "forecast" / "results" / "forecast_eval.json",
]


def load_backtest_payload(path: Path | None = None) -> dict:
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    for c in DEFAULT_CANDIDATES:
        if c.exists():
            return json.loads(c.read_text(encoding="utf-8"))
    return {
        "window": {},
        "strategies": {},
        "note": "No results JSON found — run packages/backtest CLI or forecast eval first.",
    }


def strategies_frame(payload: dict) -> pd.DataFrame:
    rows = []
    for name, m in (payload.get("strategies") or {}).items():
        if not isinstance(m, dict):
            continue
        row = {"strategy": name}
        row.update(m)
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=["strategy", "final_cash_eur", "capture_vs_pf_pct"])
    return pd.DataFrame(rows)
