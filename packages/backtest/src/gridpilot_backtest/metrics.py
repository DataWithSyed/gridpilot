"""Backtest metrics from equity / daily PnL series."""
from __future__ import annotations

import numpy as np
import pandas as pd


def historical_cvar(daily: pd.Series, alpha: float = 0.05) -> float:
    s = pd.Series(daily).dropna().astype(float)
    if s.empty:
        return float("nan")
    q = s.quantile(alpha)
    return float(-(s[s <= q].mean()))


def max_drawdown(equity: pd.Series) -> float:
    eq = pd.Series(equity).dropna().astype(float)
    if eq.empty:
        return float("nan")
    return float((eq.cummax() - eq).max())


def summarise(daily: pd.Series, equity: pd.Series, final_cash: float, cycles: float, killed: bool) -> dict:
    d = pd.Series(daily).dropna().astype(float)
    return {
        "final_cash_eur": float(final_cash),
        "n_days": int(len(d)),
        "daily_pnl_p10": float(d.quantile(0.1)) if len(d) else None,
        "daily_pnl_p50": float(d.quantile(0.5)) if len(d) else None,
        "daily_pnl_p90": float(d.quantile(0.9)) if len(d) else None,
        "cvar_5pct_loss_daily": historical_cvar(d),
        "max_drawdown_eur": max_drawdown(equity),
        "cycles": float(cycles),
        "killed": bool(killed),
    }
