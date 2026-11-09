"""Conformal / quantile calibration for GridPilot P10/P50/P90 (paper trading).

Ideas linked from Romano et al. CQR and the public de-wind-probabilistic-forecasting
repo — implemented here as a small self-contained module (not a copy of that pipeline).

Ex-ante rule: when calibrating for delivery day D, only residuals from days
≤ D - ``delay`` are used (default delay=2 so D-1 outcomes are known at noon D-1
only after D-2 settles; we use delay=2 conservatively).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """Finite-sample corrected (1 - alpha) empirical quantile of scores."""
    s = np.sort(np.asarray(scores, float)[~np.isnan(scores)])
    n = len(s)
    if n == 0:
        return 0.0
    if alpha <= 0:
        return float("inf")
    if alpha >= 1:
        return float("-inf")
    k = int(np.ceil((1.0 - alpha) * (n + 1)))
    return float(s[min(max(k, 1), n) - 1]) if k <= n else float("inf")


def cqr_scores(y: np.ndarray, q_lo: np.ndarray, q_hi: np.ndarray) -> np.ndarray:
    y, q_lo, q_hi = (np.asarray(a, float) for a in (y, q_lo, q_hi))
    return np.maximum(q_lo - y, y - q_hi)


def coverage(y: np.ndarray, q_lo: np.ndarray, q_hi: np.ndarray) -> float:
    y, q_lo, q_hi = (np.asarray(a, float) for a in (y, q_lo, q_hi))
    m = ~np.isnan(y) & ~np.isnan(q_lo) & ~np.isnan(q_hi)
    if not m.any():
        return float("nan")
    return float(np.mean((y[m] >= q_lo[m]) & (y[m] <= q_hi[m])))


def interval_score(y: np.ndarray, q_lo: np.ndarray, q_hi: np.ndarray, alpha: float = 0.2) -> float:
    """Winkler / interval score at level 1-alpha (lower is better)."""
    y, q_lo, q_hi = (np.asarray(a, float) for a in (y, q_lo, q_hi))
    m = ~np.isnan(y) & ~np.isnan(q_lo) & ~np.isnan(q_hi)
    if not m.any():
        return float("nan")
    y, lo, hi = y[m], q_lo[m], q_hi[m]
    width = hi - lo
    below = (lo - y) * (y < lo)
    above = (y - hi) * (y > hi)
    return float(np.mean(width + (2.0 / alpha) * (below + above)))


def reliability_table(
    y: np.ndarray,
    quantiles: dict[float, np.ndarray],
) -> dict[float, float]:
    """Empirical frequency of y <= q_tau for each tau (calibration / PIT proxy)."""
    y = np.asarray(y, float)
    out = {}
    for tau, q in quantiles.items():
        q = np.asarray(q, float)
        m = ~np.isnan(y) & ~np.isnan(q)
        out[float(tau)] = float(np.mean(y[m] <= q[m])) if m.any() else float("nan")
    return out


@dataclass
class RollingCQR:
    """Rolling conformalized quantile regression for P10/P90 around a P50 path.

    Stores per-day residuals after each realised day; ``calibrate`` widens/narrows
    the P10–P90 band using past scores only (delay-aware).
    """

    alpha: float = 0.20  # 80% nominal interval ≈ P10–P90
    window_days: int = 60
    delay: int = 2
    _day_scores: dict = field(default_factory=dict, repr=False)

    def observe_day(self, day: pd.Timestamp, y: np.ndarray, q_lo: np.ndarray, q_hi: np.ndarray) -> None:
        day = pd.Timestamp(day).normalize()
        sc = cqr_scores(y, q_lo, q_hi)
        # Store mean daily score (hourly exchangeability fails; day-block is ASSUMED)
        self._day_scores[day] = float(np.nanmean(sc))

    def margin_for(self, day: pd.Timestamp) -> float:
        day = pd.Timestamp(day).normalize()
        hist = [
            self._day_scores[d]
            for d in sorted(self._day_scores)
            if d <= day - pd.Timedelta(days=self.delay)
            and d > day - pd.Timedelta(days=self.delay + self.window_days)
        ]
        if len(hist) < 5:
            return 0.0
        return conformal_quantile(np.asarray(hist, float), self.alpha)

    def calibrate(
        self,
        day: pd.Timestamp,
        pred: dict[float, np.ndarray],
    ) -> dict[float, np.ndarray]:
        """Return a copy of ``pred`` with P10/P90 expanded/shrunk by CQR margin."""
        out = {q: np.asarray(v, float).copy() for q, v in pred.items()}
        if 0.10 not in out or 0.90 not in out:
            return out
        qhat = self.margin_for(day)
        if not np.isfinite(qhat):
            qhat = 0.0
        out[0.10] = out[0.10] - qhat
        out[0.90] = out[0.90] + qhat
        # Keep P50; enforce monotone
        if 0.50 in out:
            out[0.50] = np.minimum(np.maximum(out[0.50], out[0.10]), out[0.90])
        else:
            out[0.10] = np.minimum(out[0.10], out[0.90])
        return out
