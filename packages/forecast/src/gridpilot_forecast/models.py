"""Forecast models: naive, LEAR-lite (price-only), quantile GBM, ensemble.

Inspired by Lago et al. (2021) LEAR and the public de-day-ahead-price-forecasting
repo, but **price-lag + calendar only** (no TSO residual-load features here).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LassoLarsIC

from gridpilot_forecast.features import GBM_COLS, daily_panel, gbm_frame_for_day, lear_row, to_berlin


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
        lag = 7 if day.dayofweek in (0, 5, 6) else 1
        prev = day - pd.Timedelta(days=lag)
        if prev not in panel.index or panel.loc[prev].isna().any():
            return None
        return panel.loc[prev].to_numpy(float)



def _compact_hour_features(panel: pd.DataFrame, day: pd.Timestamp, hour: int) -> np.ndarray | None:
    """~15 features for one hour — identifiable on short train windows."""
    from gridpilot_forecast.features import calendar_row

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
    return np.concatenate([
        np.array([float(p1.iloc[hour]), float(p2.iloc[hour]), float(p7.iloc[hour]),
                  float(p1.mean()), float(p1.min()), float(p1.max())], dtype=float),
        dow,
        np.array([cal["month"], cal["holiday"]], dtype=float),
    ])


@dataclass
class LEARLite:
    """24 hourly LassoLarsIC models on asinh-scaled price-lag features (LEAR-lite)."""

    name: str = "lear_lite"
    models: list = field(default_factory=list, repr=False)
    sx: AsinhScaler | None = field(default=None, repr=False)
    sy: AsinhScaler | None = field(default=None, repr=False)
    _mode: str | None = field(default=None, repr=False)
    _compact_scalers: list = field(default_factory=list, repr=False)

    def fit(self, panel: pd.DataFrame, train_days: list[pd.Timestamp]) -> "LEARLite":
        """Fit 24 hourly LassoLarsIC models.

        Uses the wide ``lear_row`` design when n_samples > n_features; otherwise
        falls back to a compact same-hour lag design so AIC noise variance is
        identifiable on short windows (ASSUMED compact set for demo samples).
        """
        X_rows, Y_rows, compact_rows = [], [], []
        for day in train_days:
            day = pd.Timestamp(day).normalize()
            if day not in panel.index or panel.loc[day].isna().any():
                continue
            x = lear_row(panel, day)
            if x is None:
                continue
            X_rows.append(x)
            Y_rows.append(panel.loc[day].to_numpy(float))
            # compact: for stacking later we still store Y; compact X built per hour
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
        # Prefer wide design when identifiable; else compact per-hour features
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
            self._compact_days = None
            self._panel_ref = None
        else:
            # Compact design matrix per hour: [p_d1_h, p_d2_h, p_d7_h, mean, min, max, dow0..6, month, holiday]
            self.sx = None
            self._compact_days = compact_rows
            self._panel_ref = panel
            self._compact_scalers = []
            for h in range(24):
                Xh, yh = [], []
                for day, yrow in zip(compact_rows, Y_rows):
                    feat = _compact_hour_features(panel, day, h)
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
            x = lear_row(panel, day)
            if x is None or self.sx is None:
                return None
            z = self.sx.transform(x.reshape(1, -1))
            zy = np.array([m.predict(z)[0] for m in self.models], dtype=float)
            return self.sy.inverse(zy.reshape(-1, 1)).reshape(-1)
        # compact
        out = []
        for h, m in enumerate(self.models):
            feat = _compact_hour_features(panel, day, h)
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
        max_iter=120,
        max_leaf_nodes=15,
        min_samples_leaf=20,
        l2_regularization=1.0,
        random_state=seed,
    )


@dataclass
class QuantileGBM:
    """HistGradientBoosting quantile models for P10 / P50 / P90 (price-only features)."""

    name: str = "quantile_gbm"
    quantiles: tuple[float, ...] = (0.10, 0.50, 0.90)
    models: dict = field(default_factory=dict, repr=False)

    def fit(self, panel: pd.DataFrame, train_days: list[pd.Timestamp]) -> "QuantileGBM":
        frames, ys = [], []
        for day in train_days:
            day = pd.Timestamp(day).normalize()
            if day not in panel.index or panel.loc[day].isna().any():
                continue
            f = gbm_frame_for_day(panel, day)
            if f is None:
                continue
            frames.append(f)
            ys.append(panel.loc[day].to_numpy(float))
        self.models = {}
        if len(frames) < 14:
            return self
        X = pd.concat(frames, ignore_index=True)[GBM_COLS]
        y = np.concatenate(ys)
        for q in self.quantiles:
            m = _make_qgbm(q)
            m.fit(X, y)
            self.models[q] = m
        return self

    def predict_day(self, panel: pd.DataFrame, day: pd.Timestamp) -> dict[float, np.ndarray] | None:
        if not self.models:
            return None
        f = gbm_frame_for_day(panel, day)
        if f is None:
            return None
        X = f[GBM_COLS]
        out = {q: m.predict(X).astype(float) for q, m in self.models.items()}
        # Enforce monotone P10 <= P50 <= P90
        if 0.10 in out and 0.50 in out and 0.90 in out:
            p10, p50, p90 = out[0.10], out[0.50], out[0.90]
            p50 = np.maximum(p50, p10)
            p90 = np.maximum(p90, p50)
            out[0.10], out[0.50], out[0.90] = p10, p50, p90
        return out


@dataclass
class EnsembleQuantile:
    """Mean of LEAR-lite (point → all quantiles shifted) and QuantileGBM.

    LEAR is a point model; we centre the GBM quantile fan on the LEAR point by
    shifting so that GBM P50 aligns with the ensemble P50 = 0.5*(LEAR+GBM_P50).
    ASSUMED equal weights (as in de-day-ahead-price-forecasting ensemble).
    """

    name: str = "ensemble_lear_qgbm"
    lear: LEARLite = field(default_factory=LEARLite)
    gbm: QuantileGBM = field(default_factory=QuantileGBM)

    def fit(self, panel: pd.DataFrame, train_days: list[pd.Timestamp]) -> "EnsembleQuantile":
        self.lear.fit(panel, train_days)
        self.gbm.fit(panel, train_days)
        return self

    def predict_day(self, panel: pd.DataFrame, day: pd.Timestamp) -> dict[float, np.ndarray] | None:
        g = self.gbm.predict_day(panel, day)
        lear_pt = self.lear.predict_day(panel, day)
        if g is None and lear_pt is None:
            return None
        if g is None:
            # Fan from LEAR using a tiny synthetic spread from recent vol — fallback flat
            return {0.10: lear_pt.copy(), 0.50: lear_pt.copy(), 0.90: lear_pt.copy()}
        if lear_pt is None:
            return g
        p50_g = g[0.50]
        p50 = 0.5 * (lear_pt + p50_g)
        # Preserve GBM spread around new P50
        spread_lo = p50_g - g[0.10]
        spread_hi = g[0.90] - p50_g
        return {
            0.10: p50 - spread_lo,
            0.50: p50,
            0.90: p50 + spread_hi,
        }


def mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(a, float) - np.asarray(b, float))))
