"""Moving-block bootstrap of daily price paths for scenario revenue distributions."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


def _split_days(prices: pd.Series) -> list[pd.Series]:
    prices = prices.dropna().astype(float).sort_index()
    if prices.index.tz is None:
        days = prices.groupby(prices.index.date)
    else:
        local = prices.copy()
        local.index = local.index.tz_convert("Europe/Berlin")
        days = local.groupby(local.index.date)
    return [g for _, g in days if len(g) >= 1]


def block_bootstrap_daily_paths(
    prices: pd.Series,
    *,
    n_scenarios: int = 200,
    block_days: int = 7,
    horizon_days: int | None = None,
    rng: np.random.Generator | None = None,
) -> list[pd.Series]:
    """Resample contiguous day-blocks to build synthetic price paths.

    ASSUMED default block length = 7 calendar days (captures weekly seasonality
    better than i.i.d. day draws). Horizon defaults to the number of days in
    ``prices``.
    """
    rng = rng or np.random.default_rng(0)
    days = _split_days(prices)
    if not days:
        return []
    n_days = horizon_days or len(days)
    block = max(1, min(block_days, len(days)))
    # Indices into the day list
    max_start = len(days) - block
    if max_start < 0:
        max_start = 0
    scenarios: list[pd.Series] = []
    for _ in range(n_scenarios):
        picked: list[pd.Series] = []
        while len(picked) < n_days:
            start = int(rng.integers(0, max_start + 1))
            chunk = days[start : start + block]
            for d in chunk:
                picked.append(d)
                if len(picked) >= n_days:
                    break
        # Rebuild a continuous index starting at the first real day
        pieces = []
        cursor = pd.Timestamp(days[0].index[0])
        for d in picked[:n_days]:
            vals = d.to_numpy(dtype=float)
            # Keep intra-day time-of-day from the sampled day
            new_idx = []
            for ts in d.index:
                tod = ts - ts.normalize()
                new_idx.append(cursor.normalize() + tod)
            pieces.append(pd.Series(vals, index=pd.DatetimeIndex(new_idx), name=d.name))
            cursor = cursor.normalize() + pd.Timedelta(days=1)
        scenarios.append(pd.concat(pieces).sort_index())
    return scenarios


def scenario_revenue_distribution(
    prices: pd.Series,
    pnl_fn: Callable[[pd.Series], float],
    *,
    n_scenarios: int = 200,
    block_days: int = 7,
    horizon_days: int | None = None,
    rng: np.random.Generator | None = None,
) -> pd.Series:
    """Apply ``pnl_fn`` to each bootstrapped path; return scenario totals.

    ``pnl_fn`` must be pure / side-effect free and return a scalar EUR total
    for the path (e.g. paper-agent final cash).
    """
    paths = block_bootstrap_daily_paths(
        prices,
        n_scenarios=n_scenarios,
        block_days=block_days,
        horizon_days=horizon_days,
        rng=rng,
    )
    vals = [float(pnl_fn(p)) for p in paths]
    return pd.Series(vals, name="scenario_pnl_eur")
