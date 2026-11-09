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


def block_bootstrap_mean_diff_ci(
    daily_a: pd.Series,
    daily_b: pd.Series,
    *,
    block: int = 7,
    n_boot: int = 400,
    alpha: float = 0.10,
    seed: int = 0,
) -> dict:
    """Moving-block bootstrap CI for mean(daily_a - daily_b).

    Aligns on the intersection of dates. ``block`` days (ASSUMED weekly dependence).
    Returns mean diff and (1-alpha) percentile CI.
    """
    a = pd.Series(daily_a).dropna().astype(float)
    b = pd.Series(daily_b).dropna().astype(float)
    idx = a.index.intersection(b.index)
    if len(idx) < block * 2:
        return {
            "n_days": int(len(idx)),
            "mean_diff": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "block": block,
            "n_boot": n_boot,
        }
    diff = (a.loc[idx] - b.loc[idx]).to_numpy(float)
    n = len(diff)
    rng = np.random.default_rng(seed)
    means = []
    n_blocks = int(np.ceil(n / block))
    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        sample = np.concatenate([diff[s : s + block] for s in starts])[:n]
        means.append(float(np.mean(sample)))
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {
        "n_days": n,
        "mean_diff": float(np.mean(diff)),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "block": block,
        "n_boot": n_boot,
        "alpha": alpha,
    }
