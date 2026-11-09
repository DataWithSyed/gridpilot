"""Walk-forward quantile forecaster with the same forecast_day interface as strategies pack."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gridpilot_forecast.features import daily_panel, to_berlin
from gridpilot_forecast.models import EnsembleQuantile, NaiveDayAhead


def _as_naive_day(ts) -> pd.Timestamp:
    """Calendar date as tz-naive midnight (panel index convention)."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("Europe/Berlin")
    return pd.Timestamp(t.date())


@dataclass
class WalkForwardQuantileForecast:
    """Causal day-ahead P10/P50/P90 forecast with daily (or weekly) refits.

    Implements ``forecast_day(history, remaining_index) -> {q: Series}`` so it can
    plug into ``ForecastDrivenLP`` / ``RiskAwareForecastLP`` from gridpilot-strategies.

    Training uses a rolling lookback of completed **calendar days** only (ex-ante).
    """

    lookback_days: int = 45  # ASSUMED; short sample in umbrella demos
    refit_every_days: int = 1  # 1 = daily; raise to 7 to save compute
    min_train_days: int = 14
    quantiles: tuple[float, ...] = (0.10, 0.50, 0.90)
    model_name: str = "ensemble_lear_qgbm"
    _panel_cache_key: object | None = field(default=None, repr=False)
    _panel: pd.DataFrame | None = field(default=None, repr=False)
    _model: EnsembleQuantile | None = field(default=None, repr=False)
    _model_day: pd.Timestamp | None = field(default=None, repr=False)
    _last_fit_day: pd.Timestamp | None = field(default=None, repr=False)
    _naive: NaiveDayAhead = field(default_factory=NaiveDayAhead, repr=False)

    def _ensure_panel(self, history: pd.Series) -> pd.DataFrame:
        # Invalidate only when a new calendar day appears in history (not every hour).
        hist = to_berlin(history)
        last_day = hist.index[-1].date() if len(hist) else None
        key = (len(hist), str(last_day))
        if self._panel is None or self._panel_cache_key != key:
            self._panel = daily_panel(hist)
            self._panel_cache_key = key
        return self._panel

    def _train_days_ending(self, panel: pd.DataFrame, asof: pd.Timestamp) -> list[pd.Timestamp]:
        asof = _as_naive_day(asof)
        days = [d for d in panel.index if d < asof and not panel.loc[d].isna().any()]
        if len(days) > self.lookback_days:
            days = days[-self.lookback_days :]
        return list(days)

    def _maybe_refit(self, panel: pd.DataFrame, delivery_day: pd.Timestamp) -> None:
        delivery_day = _as_naive_day(delivery_day)
        need = self._model is None or self._last_fit_day is None
        if not need and self._last_fit_day is not None:
            need = (delivery_day - self._last_fit_day).days >= self.refit_every_days
        if not need:
            return
        train = self._train_days_ending(panel, delivery_day)
        if len(train) < self.min_train_days:
            self._model = None
            self._last_fit_day = delivery_day
            return
        m = EnsembleQuantile()
        m.fit(panel, train)
        self._model = m
        self._last_fit_day = delivery_day

    def predict_quantiles_for_day(self, history: pd.Series, day: pd.Timestamp) -> dict[float, np.ndarray]:
        panel = self._ensure_panel(history)
        day = _as_naive_day(day)
        self._maybe_refit(panel, day)
        pred = None
        if self._model is not None:
            pred = self._model.predict_day(panel, day)
        if pred is None:
            naive = self._naive.predict_day(panel, day)
            if naive is None:
                last = float(to_berlin(history).iloc[-1]) if len(history) else 0.0
                naive = np.full(24, last, dtype=float)
            pred = {q: naive.copy() for q in self.quantiles}
        return pred

    def forecast_day(
        self,
        history: pd.Series,
        remaining_index: pd.DatetimeIndex,
    ) -> dict[float, pd.Series]:
        """Interface compatible with RollingQuantilePriceForecast."""
        if len(remaining_index) == 0:
            return {q: pd.Series(dtype=float) for q in self.quantiles}
        ts0 = remaining_index[0]
        day = _as_naive_day(ts0)
        pred = self.predict_quantiles_for_day(history, day)
        out: dict[float, pd.Series] = {}
        for q in self.quantiles:
            arr = pred.get(q)
            if arr is None:
                arr = pred[0.50]
            vals = []
            for ts in remaining_index:
                h = ts.tz_convert("Europe/Berlin").hour if ts.tzinfo else pd.Timestamp(ts).hour
                vals.append(float(arr[h]) if h < len(arr) else float(arr[-1]))
            out[q] = pd.Series(vals, index=remaining_index, dtype=float)
        return out
