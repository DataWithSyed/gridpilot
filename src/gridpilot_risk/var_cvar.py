"""Historical VaR / CVaR helpers on PnL or return series."""
from __future__ import annotations

import numpy as np
import pandas as pd


def historical_var(pnl: pd.Series | np.ndarray, alpha: float = 0.05) -> float:
    """VaR at level alpha as a **loss** (positive => loss of that magnitude).

    For a PnL series, VaR_alpha = -quantile_alpha(PnL).
    """
    x = np.asarray(pd.Series(pnl).dropna(), dtype=float)
    if x.size == 0:
        return float("nan")
    q = float(np.quantile(x, alpha))
    return float(-q)


def historical_cvar(pnl: pd.Series | np.ndarray, alpha: float = 0.05) -> float:
    """CVaR / Expected Shortfall at level alpha as a **loss**.

    Mean of losses in the left tail (PnL <= quantile_alpha).
    """
    x = np.asarray(pd.Series(pnl).dropna(), dtype=float)
    if x.size == 0:
        return float("nan")
    q = float(np.quantile(x, alpha))
    tail = x[x <= q]
    if tail.size == 0:
        return float(-q)
    return float(-tail.mean())


def distribution_summary(pnl: pd.Series | np.ndarray) -> dict[str, float]:
    x = pd.Series(pnl).dropna().astype(float)
    if x.empty:
        return {}
    return {
        "n": float(len(x)),
        "mean": float(x.mean()),
        "std": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
        "p10": float(x.quantile(0.10)),
        "p50": float(x.quantile(0.50)),
        "p90": float(x.quantile(0.90)),
        "var_5pct_loss": historical_var(x, 0.05),
        "cvar_5pct_loss": historical_cvar(x, 0.05),
        "var_10pct_loss": historical_var(x, 0.10),
        "cvar_10pct_loss": historical_cvar(x, 0.10),
    }
