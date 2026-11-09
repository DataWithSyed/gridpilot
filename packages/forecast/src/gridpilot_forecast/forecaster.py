"""Walk-forward quantile forecaster with optional fundamentals + conformal calibration."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gridpilot_forecast.conformal import (
    MondrianAsymmetricCQR,
    RollingCQR,
    coverage,
    hour_bucket,
    reliability_table,
    residual_load_regime,
)
from gridpilot_forecast.features import daily_panel, to_berlin
from gridpilot_forecast.models import EnsembleQuantile, NaiveDayAhead


def _as_naive_day(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("Europe/Berlin")
    return pd.Timestamp(t.date())


@dataclass
class WalkForwardQuantileForecast:
    """Causal day-ahead P10/P50/P90 forecast with daily/weekly refits.

    Implements ``forecast_day(history, remaining_index) -> {q: Series}`` so it can
    plug into ``ForecastDrivenLP`` / ``RiskAwareForecastLP``.

    When ``fundamentals`` panels are set, day-ahead residual-load features are used.
    When ``calibrate`` is True, rolling CQR widens/narrows P10–P90 using past residuals only.
    """

    lookback_days: int = 90  # ASSUMED; longer window than the short demo
    refit_every_days: int = 7  # ASSUMED compute tradeoff on 12-month runs
    min_train_days: int = 21
    quantiles: tuple[float, ...] = (0.10, 0.50, 0.90)
    use_fundamentals: bool = False
    calibrate: bool = True
    calibrator_kind: str = "rolling"  # rolling | mondrian
    conformal_window_days: int = 60
    conformal_delay: int = 2
    model_name: str = "ensemble_lear_qgbm"
    fundamentals: dict | None = field(default=None, repr=False)
    _panel_cache_key: object | None = field(default=None, repr=False)
    _panel: pd.DataFrame | None = field(default=None, repr=False)
    _model: EnsembleQuantile | None = field(default=None, repr=False)
    _last_fit_day: pd.Timestamp | None = field(default=None, repr=False)
    _naive: NaiveDayAhead = field(default_factory=NaiveDayAhead, repr=False)
    _cqr: RollingCQR | None = field(default=None, repr=False)
    _last_raw_pred: dict | None = field(default=None, repr=False)
    _last_pred_day: pd.Timestamp | None = field(default=None, repr=False)
    calibration_log: list = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.calibrate:
            if self.calibrator_kind == "mondrian":
                self._cqr = MondrianAsymmetricCQR(
                    alpha=0.20,
                    window_days=self.conformal_window_days,
                    delay=self.conformal_delay,
                )
            else:
                self._cqr = RollingCQR(
                    alpha=0.20,
                    window_days=self.conformal_window_days,
                    delay=self.conformal_delay,
                )

    def set_fundamentals(self, fund: dict[str, pd.DataFrame] | None) -> None:
        self.fundamentals = fund
        self.use_fundamentals = fund is not None
        # Force refit on next call
        self._model = None
        self._last_fit_day = None

    def _ensure_panel(self, history: pd.Series) -> pd.DataFrame:
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
        fund = self.fundamentals if self.use_fundamentals else None
        m = EnsembleQuantile(use_fundamentals=bool(fund))
        m.fit(panel, train, fund=fund)
        self._model = m
        self._last_fit_day = delivery_day

    def _ensure_rl_edges(self) -> tuple[float, float] | None:
        """Tercile edges of daily mean residual-load forecast (ex-ante panel only)."""
        edges = getattr(self, "_rl_edges", None)
        if edges is not None:
            return edges
        if not self.fundamentals or "residual_load_fc" not in self.fundamentals:
            self._rl_edges = None
            return None
        rl = self.fundamentals["residual_load_fc"]
        daily = rl.mean(axis=1).dropna()
        if len(daily) < 30:
            self._rl_edges = None
            return None
        q33, q66 = np.nanpercentile(daily.to_numpy(float), [33.3, 66.6])
        self._rl_edges = (float(q33), float(q66))
        return self._rl_edges

    def _mondrian_regime_for_day(self, day: pd.Timestamp, n_hours: int) -> tuple[str, np.ndarray | None]:
        """Return (day_regime, hour_regimes_or_None)."""
        edges = self._ensure_rl_edges()
        if edges is not None and self.fundamentals and "residual_load_fc" in self.fundamentals:
            rl = self.fundamentals["residual_load_fc"]
            if day in rl.index:
                day_rl = float(np.nanmean(rl.loc[day].to_numpy(float)))
                return residual_load_regime(day_rl, edges), None
        hour_regs = np.array([hour_bucket(h) for h in range(n_hours)])
        return "hourly", hour_regs

    def _observe_realized(self, panel: pd.DataFrame, delivery_day: pd.Timestamp) -> None:
        """Feed CQR with recently realised days (ex-ante delay handled inside calibrator)."""
        if self._cqr is None or self._last_raw_pred is None or self._last_pred_day is None:
            return
        prev = _as_naive_day(delivery_day) - pd.Timedelta(days=1)
        if isinstance(self._cqr, MondrianAsymmetricCQR):
            already = prev in self._cqr._lower
        else:
            already = prev in getattr(self._cqr, "_day_scores", {})
        if prev not in panel.index or prev != self._last_pred_day or already:
            return
        y = panel.loc[prev].to_numpy(float)
        raw = self._last_raw_pred
        if 0.10 not in raw or 0.90 not in raw or np.isnan(y).any():
            return
        if isinstance(self._cqr, MondrianAsymmetricCQR):
            regime, hour_regs = self._mondrian_regime_for_day(prev, len(y))
            if hour_regs is not None:
                self._cqr.observe_day(
                    prev, y, raw[0.10], raw[0.90], q_p50=raw.get(0.50), hour_regimes=hour_regs
                )
            else:
                self._cqr.observe_day(
                    prev, y, raw[0.10], raw[0.90], regime=regime, q_p50=raw.get(0.50)
                )
        else:
            self._cqr.observe_day(prev, y, raw[0.10], raw[0.90])

    def predict_quantiles_for_day(self, history: pd.Series, day: pd.Timestamp) -> dict[float, np.ndarray]:
        panel = self._ensure_panel(history)
        day = _as_naive_day(day)
        self._observe_realized(panel, day)
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
        self._last_raw_pred = {q: np.asarray(v, float).copy() for q, v in pred.items()}
        self._last_pred_day = day
        if self._cqr is not None and self.calibrate:
            if isinstance(self._cqr, MondrianAsymmetricCQR):
                regime, hour_regs = self._mondrian_regime_for_day(day, len(next(iter(pred.values()))))
                pred = self._cqr.calibrate(day, pred, regime=regime, hour_regimes=hour_regs)
            else:
                pred = self._cqr.calibrate(day, pred)
        return pred

    def forecast_day(
        self,
        history: pd.Series,
        remaining_index: pd.DatetimeIndex,
    ) -> dict[float, pd.Series]:
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


def evaluate_calibration(
    y_by_day: dict[pd.Timestamp, np.ndarray],
    pred_by_day: dict[pd.Timestamp, dict[float, np.ndarray]],
) -> dict:
    """Coverage + reliability for a set of day-ahead quantile forecasts."""
    ys, los, his, p10s, p50s, p90s = [], [], [], [], [], []
    for d, y in y_by_day.items():
        if d not in pred_by_day:
            continue
        p = pred_by_day[d]
        ys.append(np.asarray(y, float))
        los.append(np.asarray(p[0.10], float))
        his.append(np.asarray(p[0.90], float))
        p10s.append(p[0.10])
        p50s.append(p[0.50])
        p90s.append(p[0.90])
    if not ys:
        return {"n_days": 0}
    y = np.concatenate(ys)
    lo = np.concatenate(los)
    hi = np.concatenate(his)
    rel = reliability_table(
        y,
        {
            0.10: np.concatenate(p10s),
            0.50: np.concatenate(p50s),
            0.90: np.concatenate(p90s),
        },
    )
    return {
        "n_days": len(ys),
        "n_hours": int(len(y)),
        "coverage_80": coverage(y, lo, hi),
        "reliability": {str(k): v for k, v in rel.items()},
        "nominal_80": 0.80,
    }
