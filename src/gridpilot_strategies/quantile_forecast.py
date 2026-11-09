"""Causal rolling quantile price forecasts (hour-of-day climatology)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RollingQuantilePriceForecast:
    """Forecast remaining hours of the day from same-hour historical quantiles.

    Ex-ante: uses only ``history`` up to (and including) the current bar.
    Quantiles are computed over a rolling lookback of completed hours, grouped
    by hour-of-day in Europe/Berlin. This is a simple climatological baseline,
    not an ML model — honest and reproducible for walk-forward evaluation.
    """

    lookback_hours: int = 24 * 28  # ASSUMED 28-day lookback
    quantiles: tuple[float, ...] = (0.10, 0.50, 0.90)

    def forecast_day(
        self,
        history: pd.Series,
        remaining_index: pd.DatetimeIndex,
    ) -> dict[float, pd.Series]:
        """Return {q: Series} forecasts aligned to ``remaining_index``."""
        hist = history.dropna().astype(float)
        if hist.index.tz is not None:
            hist = hist.copy()
            hist.index = hist.index.tz_convert("Europe/Berlin")
        window = hist.iloc[-self.lookback_hours :]
        out: dict[float, pd.Series] = {}
        if len(window) < 24:
            # Not enough history: flat last price
            last = float(hist.iloc[-1]) if len(hist) else 0.0
            for q in self.quantiles:
                out[q] = pd.Series(last, index=remaining_index, dtype=float)
            return out

        by_hour = window.groupby(window.index.hour)
        for q in self.quantiles:
            vals = []
            for ts in remaining_index:
                h = ts.tz_convert("Europe/Berlin").hour if ts.tzinfo else ts.hour
                if h in by_hour.groups and len(by_hour.get_group(h)) >= 3:
                    vals.append(float(by_hour.get_group(h).quantile(q)))
                else:
                    vals.append(float(window.quantile(q)))
            out[q] = pd.Series(vals, index=remaining_index, dtype=float)
        return out
