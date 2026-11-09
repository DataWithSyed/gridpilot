import numpy as np
import pandas as pd

from gridpilot_risk.bootstrap import block_bootstrap_daily_paths, scenario_revenue_distribution
from gridpilot_risk.var_cvar import distribution_summary


def _synthetic_prices(n_days: int = 21) -> pd.Series:
    idx = pd.date_range("2026-08-01", periods=n_days * 24, freq="h", tz="Europe/Berlin")
    # mild daily shape
    hour = idx.hour
    vals = 100 + 40 * np.sin((hour - 6) / 24 * 2 * np.pi) + np.linspace(0, 5, len(idx))
    return pd.Series(vals, index=idx, name="da_price_eur_mwh")


def test_bootstrap_shape():
    prices = _synthetic_prices(14)
    paths = block_bootstrap_daily_paths(prices, n_scenarios=5, block_days=3, horizon_days=7, rng=np.random.default_rng(1))
    assert len(paths) == 5
    for p in paths:
        # ~7 days of hourly bars
        assert 6 * 24 <= len(p) <= 8 * 24


def test_scenario_revenue_distribution():
    prices = _synthetic_prices(10)

    def pnl_fn(s: pd.Series) -> float:
        return float(s.mean() * 10)  # toy: proportional to mean price

    dist = scenario_revenue_distribution(prices, pnl_fn, n_scenarios=20, block_days=2, horizon_days=5, rng=np.random.default_rng(2))
    assert len(dist) == 20
    summary = distribution_summary(dist)
    assert summary["p50"] > 0
    assert summary["cvar_5pct_loss"] >= summary["var_5pct_loss"] - 1e-6
