import pandas as pd

from gridpilot_core.risk_stats import daily_pnl, summary_distribution


def test_daily_pnl_and_percentiles():
    idx = pd.date_range("2026-08-01", periods=48, freq="h", tz="Europe/Berlin")
    equity = pd.Series(range(48), index=idx, dtype=float)
    d = daily_pnl(equity)
    assert len(d) == 1  # only one day-to-day diff across 2 calendar days → 1 pnl
    # Build multi-day
    idx2 = pd.date_range("2026-08-01", periods=5, freq="D", tz="Europe/Berlin")
    eq2 = pd.Series([0.0, 10.0, 5.0, 20.0, 18.0], index=idx2)
    d2 = daily_pnl(eq2)
    s = summary_distribution(d2)
    assert s["n_days"] == 4
    assert s["p50"] == s["p50"]  # finite
