"""Rolling-window PnL distribution helpers (P50 / P90)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def daily_pnl(equity: pd.Series) -> pd.Series:
    """Map timestamped equity to daily PnL (last equity of day − previous day)."""
    if equity.empty:
        return pd.Series(dtype=float, name="daily_pnl")
    eq = equity.sort_index()
    # Local calendar day in the series timezone (Europe/Berlin expected)
    days = eq.groupby(eq.index.date).last()
    pnl = days.diff().dropna()
    pnl.index = pd.to_datetime(pnl.index)
    return pnl.rename("daily_pnl")


def rolling_pnl_percentiles(
    daily: pd.Series,
    *,
    window: int = 7,
    percentiles: tuple[float, ...] = (10.0, 50.0, 90.0),
) -> pd.DataFrame:
    """Rolling distribution of daily PnL. P90 here is the 90th percentile (upside).

    For risk language, also report P10 as a downside reference. Labels are explicit.
    """
    daily = daily.dropna().astype(float)
    rows = []
    for i in range(len(daily)):
        w = daily.iloc[max(0, i + 1 - window) : i + 1]
        if len(w) < max(3, window // 2):
            continue
        rec = {"date": daily.index[i], "n": len(w), "mean": float(w.mean())}
        for p in percentiles:
            rec[f"p{int(p)}"] = float(np.percentile(w.to_numpy(), p))
        rows.append(rec)
    if not rows:
        cols = ["date", "n", "mean"] + [f"p{int(p)}" for p in percentiles]
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).set_index("date")


def summary_distribution(daily: pd.Series) -> dict[str, float]:
    """Full-sample P10 / P50 / P90 / mean of daily PnL (EUR)."""
    x = daily.dropna().astype(float).to_numpy()
    if len(x) == 0:
        return {"n_days": 0.0, "mean": float("nan"), "p10": float("nan"), "p50": float("nan"), "p90": float("nan")}
    return {
        "n_days": float(len(x)),
        "mean": float(np.mean(x)),
        "p10": float(np.percentile(x, 10)),
        "p50": float(np.percentile(x, 50)),
        "p90": float(np.percentile(x, 90)),
    }
