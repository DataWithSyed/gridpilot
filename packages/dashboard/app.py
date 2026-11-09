"""Thin Streamlit entrypoint. Logic lives in gridpilot_dashboard.

Run: streamlit run packages/dashboard/app.py
Paper trading only — no live order placement.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import streamlit as st

from gridpilot_dashboard.data import load_backtest_payload, strategies_frame
from gridpilot_dashboard.health import health_check


def main() -> None:
    st.set_page_config(page_title="GridPilot", layout="wide")
    st.title("GridPilot — paper-trading ops view")
    st.caption("Paper trading only. No real orders. Energy-Charts / SMARD CC BY 4.0.")
    hc = health_check()
    st.sidebar.write("Health:", "✅" if hc["ok"] else "❌", hc["reason"])
    payload = load_backtest_payload()
    win = payload.get("window") or {}
    st.write(
        f"Window: **{win.get('start', '?')} → {win.get('end', '?')}** "
        f"({win.get('n_hours', '?')} hours; DA mean {win.get('da_mean_eur_mwh', float('nan')):.2f} €/MWh)"
        if win.get("da_mean_eur_mwh") is not None
        else f"Window: **{win.get('start', '?')} → {win.get('end', '?')}** ({win.get('n_hours', '?')} hours)"
    )
    df = strategies_frame(payload)
    if df.empty:
        st.warning("No backtest results yet. Run `python packages/forecast/scripts/run_long_window_eval.py` first.")
        return
    show = df.copy()
    prefer = [
        "strategy",
        "final_cash_eur",
        "capture_vs_pf_pct",
        "daily_pnl_p10",
        "daily_pnl_p50",
        "daily_pnl_p90",
        "cvar_5pct_loss_daily",
        "max_drawdown_eur",
        "cycles",
    ]
    cols = [c for c in prefer if c in show.columns]
    st.subheader("Strategy comparison")
    st.dataframe(show[cols], width="stretch")
    if "final_cash_eur" in show.columns:
        st.subheader("Final cash (EUR)")
        st.bar_chart(show.set_index("strategy")["final_cash_eur"])
    if "daily_pnl_p10" in show.columns and "daily_pnl_p90" in show.columns:
        st.subheader("Daily PnL P10 / P50 / P90")
        st.bar_chart(show.set_index("strategy")[["daily_pnl_p10", "daily_pnl_p50", "daily_pnl_p90"]])

    mae = payload.get("forecast_mae") or {}
    cal = (mae.get("calibration") or {}) if isinstance(mae, dict) else {}
    if cal:
        st.subheader("Forecast calibration (80% interval)")
        st.write(
            f"Raw coverage **{100*cal.get('raw_coverage_80', float('nan')):.1f}%** → "
            f"CQR **{100*cal.get('cqr_coverage_80', float('nan')):.1f}%** "
            f"(nominal 80%; n={cal.get('n_hours', '?')} hours)"
        )
        rel = cal.get("cqr_reliability") or {}
        if rel:
            st.write("Reliability (empirical ≤ qτ):", {k: round(v, 3) for k, v in rel.items()})

    boot = payload.get("bootstrap_vs_threshold") or {}
    if boot:
        st.subheader("Bootstrap mean daily PnL vs threshold (90% CI, block=7d)")
        brows = [{"strategy": k, **v} for k, v in boot.items()]
        st.dataframe(pd.DataFrame(brows), width="stretch")

    lim = payload.get("assumptions") or payload.get("limitations") or [
        "Paper trading only",
        "Hourly resample; no fees/slippage",
    ]
    st.subheader("Assumptions / limitations")
    for line in lim:
        st.write(f"- {line}")
    st.caption(payload.get("attribution", "Energy-Charts / SMARD — CC BY 4.0"))


if __name__ == "__main__":
    main()
