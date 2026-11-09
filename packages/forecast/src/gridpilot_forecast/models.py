"""Forecast models: naive, LEAR-lite, quantile GBM, ensemble.

Inspired by Lago et al. (2021) LEAR and the public de-day-ahead-price-forecasting
repo. When fundamentals panels are supplied, day-ahead residual-load / renewables
features are included (ex-ante). Otherwise price-lag + calendar only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LassoLarsIC

from gridpilot_forecast.features import (
    GBM_COLS,
    GBM_COLS_FUND,
    calendar_row,
    gbm_frame_for_day,
    gbm_frame_for_day_with_fundamentals,
    lear_row,
    lear_row_with_fundamentals,
)


class AsinhScaler:
    """Median/MAD then asinh (handles negative prices)."""

    def fit(self, x: np.ndarray) -> "AsinhScaler":
        x = np.asarray(x, float)
        self.med = np.nanmedian(x, axis=0)
        mad = np.nanmedian(np.abs(x - self.med), axis=0) * 1.4826
        self.mad = np.where(mad > 1e-9, mad, 1.0)
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        return np.arcsinh((np.asarray(x, float) - self.med) / self.mad)

    def inverse(self, z: np.ndarray) -> np.ndarray:
        return np.sinh(z) * self.mad + self.med


@dataclass
class NaiveDayAhead:
    """Lago-style naive: D-7 on Mon/Sat/Sun else D-1."""

    name: str = "naive"

    def predict_day(self, panel: pd.DataFrame, day: pd.Timestamp) -> np.ndarray | None:
        day = pd.Timestamp(day).normalize()
        lag = 7 if day.day_of_week in (0, 5, 6) else 1
        prev = day - pd.Timedelta(days=lag)
        if prev not in panel.index or panel.loc[prev].isna().any():
            return None
        return panel.loc[prev].to_numpy(float)


def _compact_hour_features(
    panel: pd.DataFrame,
    day: pd.Timestamp,
    hour: int,
    fund: dict[str, pd.DataFrame] | None = None,
) -> np.ndarray | None:
    """Compact same-hour lag design (+ optional residual-load hour feature)."""
    day = pd.Timestamp(day).normalize()
    try:
        p1 = panel.loc[day - pd.Timedelta(days=1)]
        p2 = panel.loc[day - pd.Timedelta(days=2)]
        p7 = panel.loc[day - pd.Timedelta(days=7)]
    except KeyError:
        return None
    if p1.isna().any() or p2.isna().any() or p7.isna().any():
        return None
    cal = calendar_row(day)
    dow = np.zeros(7, dtype=float)
    dow[int(cal["dow"])] = 1.0
    parts = [
        np.array(
            [
                float(p1.iloc[hour]),
                float(p2.iloc[hour]),
                float(p7.iloc[hour]),
                float(p1.mean()),
                float(p1.min()),
                float(p1.max()),
            ],
            dtype=float,
        ),
        dow,
        np.array([cal["month"], cal["holiday"]], dtype=float),
    ]
    if fund is not None:
        rl = fund.get("residual_load_fc")
        if rl is None or day not in rl.index or rl.loc[day].isna().any():
            return None
        parts.append(
            np.array(
                [
                    float(rl.loc[day].iloc[hour]),
                    float(rl.loc[day].mean()),
                    float(fund["solar_fc"].loc[day].iloc[hour]) if "solar_fc" in fund else 0.0,
                    float(fund["wind_fc"].loc[day].iloc[hour]) if "wind_fc" in fund else 0.0,
                ],
                dtype=float,
            )
        )
    return np.concatenate(parts)


@dataclass
class LEARLite:
    """24 hourly LassoLarsIC models on asinh-scaled features."""

    name: str = "lear_lite"
    use_fundamentals: bool = False
    models: list = field(default_factory=list, repr=False)
    sx: AsinhScaler | None = field(default=None, repr=False)
    sy: AsinhScaler | None = field(default=None, repr=False)
    _mode: str | None = field(default=None, repr=False)
    _compact_scalers: list = field(default_factory=list, repr=False)
    _fund: dict | None = field(default=None, repr=False)

    def fit(
        self,
        panel: pd.DataFrame,
        train_days: list[pd.Timestamp],
        fund: dict[str, pd.DataFrame] | None = None,
    ) -> "LEARLite":
        self._fund = fund if self.use_fundamentals else None
        X_rows, Y_rows, compact_rows = [], [], []
        for day in train_days:
            day = pd.Timestamp(day).normalize()
            if day not in panel.index or panel.loc[day].isna().any():
                continue
            if self._fund is not None:
                x = lear_row_with_fundamentals(panel, self._fund, day)
            else:
                x = lear_row(panel, day)
            if x is None:
                continue
            X_rows.append(x)
            Y_rows.append(panel.loc[day].to_numpy(float))
            compact_rows.append(day)
        if len(X_rows) < 14:
            self.models = []
            self._mode = None
            return self
        X = np.asarray(X_rows, float)
        Y = np.asarray(Y_rows, float)
        self.sy = AsinhScaler().fit(Y.reshape(-1, 1))
        Zy = self.sy.transform(Y.reshape(-1, 1)).reshape(Y.shape)
        self.models = []
        use_wide = X.shape[0] > X.shape[1] + 5
        self._mode = "wide" if use_wide else "compact"
        if use_wide:
            self.sx = AsinhScaler().fit(X)
            Z = self.sx.transform(X)
            for h in range(24):
                y = Zy[:, h]
                nv = float(np.var(y)) * 0.5 + 1e-6
                m = LassoLarsIC(criterion="aic", max_iter=400, noise_variance=nv)
                m.fit(Z, y)
                self.models.append(m)
            self._compact_scalers = []
        else:
            self.sx = None
            self._compact_scalers = []
            for h in range(24):
                Xh, yh = [], []
                for day, yrow in zip(compact_rows, Y_rows):
                    feat = _compact_hour_features(panel, day, h, self._fund)
                    if feat is None:
                        continue
                    Xh.append(feat)
                    yh.append(float(yrow[h]))
                Xh = np.asarray(Xh, float)
                yh = np.asarray(yh, float)
                sx = AsinhScaler().fit(Xh)
                sy_h = AsinhScaler().fit(yh.reshape(-1, 1))
                Z = sx.transform(Xh)
                z = sy_h.transform(yh.reshape(-1, 1)).ravel()
                nv = float(np.var(z)) * 0.5 + 1e-6
                m = LassoLarsIC(criterion="aic", max_iter=400, noise_variance=nv)
                m.fit(Z, z)
                self.models.append(m)
                self._compact_scalers.append((sx, sy_h))
        return self

    def predict_day(self, panel: pd.DataFrame, day: pd.Timestamp) -> np.ndarray | None:
        if not self.models or self.sy is None:
            return None
        if getattr(self, "_mode", "wide") == "wide":
            if self._fund is not None:
                x = lear_row_with_fundamentals(panel, self._fund, day)
            else:
                x = lear_row(panel, day)
            if x is None or self.sx is None:
                return None
            z = self.sx.transform(x.reshape(1, -1))
            zy = np.array([m.predict(z)[0] for m in self.models], dtype=float)
            return self.sy.inverse(zy.reshape(-1, 1)).reshape(-1)
        out = []
        for h, m in enumerate(self.models):
            feat = _compact_hour_features(panel, day, h, self._fund)
            if feat is None:
                return None
            sx, sy_h = self._compact_scalers[h]
            z = sx.transform(feat.reshape(1, -1))
            pred = sy_h.inverse(m.predict(z).reshape(-1, 1)).ravel()[0]
            out.append(float(pred))
        return np.asarray(out, float)


def _make_qgbm(quantile: float, seed: int = 0) -> HistGradientBoostingRegressor:
    # Keep trees small for box memory / runtime.
    return HistGradientBoostingRegressor(
        loss="quantile",
        quantile=quantile,
        learning_rate=0.08,
        max_iter=100,
        max_leaf_nodes=15,
        min_samples_leaf=20,
        l2_regularization=1.0,
        random_state=seed,
    )


@dataclass
class QuantileGBM:
    """HistGradientBoosting quantile models for P10 / P50 / P90."""

    name: str = "quantile_gbm"
    use_fundamentals: bool = False
    quantiles: tuple[float, ...] = (0.10, 0.50, 0.90)
    models: dict = field(default_factory=dict, repr=False)
    _cols: list = field(default_factory=lambda: list(GBM_COLS), repr=False)
    _fund: dict | None = field(default=None, repr=False)

    def fit(
        self,
        panel: pd.DataFrame,
        train_days: list[pd.Timestamp],
        fund: dict[str, pd.DataFrame] | None = None,
    ) -> "QuantileGBM":
        self._fund = fund if self.use_fundamentals else None
        self._cols = list(GBM_COLS_FUND if self._fund is not None else GBM_COLS)
        frames, ys = [], []
        for day in train_days:
            day = pd.Timestamp(day).normalize()
            if day not in panel.index or panel.loc[day].isna().any():
                continue
            if self._fund is not None:
                f = gbm_frame_for_day_with_fundamentals(panel, self._fund, day)
            else:
                f = gbm_frame_for_day(panel, day)
            if f is None:
                continue
            frames.append(f)
            ys.append(panel.loc[day].to_numpy(float))
        self.models = {}
        if len(frames) < 14:
            return self
        X = pd.concat(frames, ignore_index=True)[self._cols]
        y = np.concatenate(ys)
        for q in self.quantiles:
            m = _make_qgbm(q)
            m.fit(X, y)
            self.models[q] = m
        return self

    def predict_day(self, panel: pd.DataFrame, day: pd.Timestamp) -> dict[float, np.ndarray] | None:
        if not self.models:
            return None
        if self._fund is not None:
            f = gbm_frame_for_day_with_fundamentals(panel, self._fund, day)
        else:
            f = gbm_frame_for_day(panel, day)
        if f is None:
            return None
        X = f[self._cols]
        out = {q: m.predict(X).astype(float) for q, m in self.models.items()}
        if 0.10 in out and 0.50 in out and 0.90 in out:
            p10, p50, p90 = out[0.10], out[0.50], out[0.90]
            p50 = np.maximum(p50, p10)
            p90 = np.maximum(p90, p50)
            out[0.10], out[0.50], out[0.90] = p10, p50, p90
        return out


@dataclass
class EnsembleQuantile:
    """Mean of LEAR-lite point and QuantileGBM fan (equal weights, ASSUMED)."""

    name: str = "ensemble_lear_qgbm"
    use_fundamentals: bool = False
    lear: LEARLite = field(default=None)  # type: ignore[assignment]
    gbm: QuantileGBM = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.lear is None:
            self.lear = LEARLite(use_fundamentals=self.use_fundamentals)
        if self.gbm is None:
            self.gbm = QuantileGBM(use_fundamentals=self.use_fundamentals)

    def fit(
        self,
        panel: pd.DataFrame,
        train_days: list[pd.Timestamp],
        fund: dict[str, pd.DataFrame] | None = None,
    ) -> "EnsembleQuantile":
        self.lear.use_fundamentals = self.use_fundamentals
        self.gbm.use_fundamentals = self.use_fundamentals
        self.lear.fit(panel, train_days, fund=fund)
        self.gbm.fit(panel, train_days, fund=fund)
        return self

    def predict_day(self, panel: pd.DataFrame, day: pd.Timestamp) -> dict[float, np.ndarray] | None:
        g = self.gbm.predict_day(panel, day)
        lear_pt = self.lear.predict_day(panel, day)
        if g is None and lear_pt is None:
            return None
        if g is None:
            return {0.10: lear_pt.copy(), 0.50: lear_pt.copy(), 0.90: lear_pt.copy()}
        if lear_pt is None:
            return g
        p50_g = g[0.50]
        p50 = 0.5 * (lear_pt + p50_g)
        spread_lo = p50_g - g[0.10]
        spread_hi = g[0.90] - p50_g
        return {
            0.10: p50 - spread_lo,
            0.50: p50,
            0.90: p50 + spread_hi,
        }


def mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(a, float) - np.asarray(b, float))))
