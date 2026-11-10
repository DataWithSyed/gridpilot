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


def residual_load_regime(residual_mw: float, edges: tuple[float, float]) -> str:
    """Map a day residual-load level to low / mid / high using fixed edges."""
    lo, hi = edges
    if residual_mw < lo:
        return "low"
    if residual_mw < hi:
        return "mid"
    return "high"


def hour_bucket(hour: int) -> str:
    """Coarse hour-of-day regime for Mondrian when fundamentals are absent."""
    h = int(hour) % 24
    if h < 6:
        return "night"
    if h < 10:
        return "morning"
    if h < 18:
        return "day"
    return "evening"




def regime_fallback_chain(regime: str) -> list[str]:
    """Parent chain for tight labels like ``evening|high|volatile``."""
    parts = [x for x in str(regime).split("|") if x]
    chain = ["|".join(parts[:i]) for i in range(len(parts), 0, -1)]
    if "all" not in chain:
        chain.append("all")
    return chain


def vol_bucket(recent_std: float, baseline_std: float) -> str:
    """Ex-ante calm/volatile split of a hour-of-day price std."""
    if not np.isfinite(recent_std) or not np.isfinite(baseline_std) or baseline_std <= 0:
        return "calm"
    return "volatile" if recent_std >= baseline_std else "calm"


def hourly_volatility_buckets(
    price_panel: pd.DataFrame,
    day: pd.Timestamp,
    n_hours: int,
    *,
    recent_days: int = 7,
    baseline_days: int = 60,
) -> np.ndarray:
    """Hour-of-day volatility labels using only days strictly before ``day``."""
    day = pd.Timestamp(day).normalize()
    past = price_panel[price_panel.index < day]
    labels = []
    for h in range(n_hours):
        col = past.iloc[:, min(h, past.shape[1] - 1)].dropna() if past.shape[1] else pd.Series(dtype=float)
        if len(col) < max(recent_days, 14):
            labels.append("calm")
            continue
        recent = float(col.iloc[-recent_days:].std(ddof=0))
        baseline = float(col.iloc[-baseline_days:].std(ddof=0))
        labels.append(vol_bucket(recent, baseline))
    return np.asarray(labels)


def tighter_hour_regimes(
    n_hours: int,
    *,
    residual_hourly: np.ndarray | None = None,
    rl_edges: tuple[float, float] | None = None,
    vol_hourly: np.ndarray | None = None,
) -> np.ndarray:
    """Hour-bucket × residual-load tercile × volatility labels (ex-ante features)."""
    labels = []
    for h in range(n_hours):
        parts = [hour_bucket(h)]
        if residual_hourly is not None and rl_edges is not None and h < len(residual_hourly):
            v = float(residual_hourly[h])
            if np.isfinite(v):
                parts.append(residual_load_regime(v, rl_edges))
        if vol_hourly is not None and h < len(vol_hourly):
            parts.append(str(vol_hourly[h]))
        labels.append("|".join(parts))
    return np.asarray(labels)


def build_tight_hour_regimes(
    day: pd.Timestamp,
    n_hours: int,
    *,
    price_panel: pd.DataFrame | None = None,
    residual_hourly: np.ndarray | None = None,
    rl_edges: tuple[float, float] | None = None,
) -> np.ndarray:
    """Convenience: tighter Mondrian labels for one delivery day."""
    vol = None
    if price_panel is not None and len(price_panel) > 0:
        vol = hourly_volatility_buckets(price_panel, day, n_hours)
    return tighter_hour_regimes(
        n_hours, residual_hourly=residual_hourly, rl_edges=rl_edges, vol_hourly=vol
    )

@dataclass
class MondrianAsymmetricCQR:
    """Regime-conditional CQR + asymmetric margins + P50 residual shift.

    Mondrian = category-conditional conformal (residual-load or hour bucket).
    Band expansion uses classic CQR scores ``max(q_lo - y, y - q_hi)`` so
    day-averaging cannot shrink intervals the way signed means would.
    Asymmetric lower/upper scores are also tracked; margins are
    ``max(0, Q(signed), Q(classic))`` so we never shrink relative to raw quantiles
    without evidence.

    Crossref-checked related refs:
    - Lei et al. DOI 10.1080/01621459.2017.1307116
    - Inductive Mondrian conformal predictors DOI 10.1007/s10994-018-5754-9
    """

    alpha: float = 0.20
    window_days: int = 60
    delay: int = 2
    p50_alpha: float = 0.50
    _classic: dict = field(default_factory=dict, repr=False)  # day -> {regime: score}
    _lower: dict = field(default_factory=dict, repr=False)
    _upper: dict = field(default_factory=dict, repr=False)
    _p50: dict = field(default_factory=dict, repr=False)
    _day_regime: dict = field(default_factory=dict, repr=False)

    def observe_day(
        self,
        day: pd.Timestamp,
        y: np.ndarray,
        q_lo: np.ndarray,
        q_hi: np.ndarray,
        *,
        regime: str = "all",
        q_p50: np.ndarray | None = None,
        hour_regimes: np.ndarray | None = None,
    ) -> None:
        day = pd.Timestamp(day).normalize()
        y = np.asarray(y, float)
        q_lo = np.asarray(q_lo, float)
        q_hi = np.asarray(q_hi, float)

        def _accumulate(lab: str, sl: slice | np.ndarray) -> None:
            yy, lo, hi = y[sl], q_lo[sl], q_hi[sl]
            if len(yy) == 0:
                return
            classic = float(np.nanmean(np.maximum(lo - yy, yy - hi)))
            lo_s = float(np.nanmean(lo - yy))
            hi_s = float(np.nanmean(yy - hi))
            self._classic.setdefault(day, {})[lab] = classic
            self._lower.setdefault(day, {})[lab] = lo_s
            self._upper.setdefault(day, {})[lab] = hi_s
            if q_p50 is not None:
                pp = np.asarray(q_p50, float)[sl]
                self._p50.setdefault(day, {})[lab] = float(np.nanmean(yy - pp))

        if hour_regimes is not None:
            labels = np.asarray([str(x) for x in hour_regimes])
            if len(labels) != len(y):
                raise ValueError("hour_regimes length must match y")
            keys: set[str] = set()
            for lab in labels:
                keys.update(regime_fallback_chain(str(lab)))
            for key in sorted(keys):
                if key == "all":
                    mask = np.ones(len(labels), dtype=bool)
                else:
                    mask = np.array(
                        [lab == key or str(lab).startswith(key + "|") for lab in labels],
                        dtype=bool,
                    )
                _accumulate(key, mask)
            self._day_regime[day] = "hourly"
        else:
            for key in regime_fallback_chain(str(regime)):
                _accumulate(key, slice(None))
            self._day_regime[day] = str(regime)

    def _hist(self, store: dict, day: pd.Timestamp, regime: str) -> list[float]:
        day = pd.Timestamp(day).normalize()
        out = []
        for d in sorted(store):
            if d > day - pd.Timedelta(days=self.delay):
                continue
            if d <= day - pd.Timedelta(days=self.delay + self.window_days):
                continue
            m = store[d]
            if regime in m:
                out.append(m[regime])
            elif "all" in m:
                out.append(m["all"])
        return out

    def margins_for(self, day: pd.Timestamp, regime: str = "all") -> tuple[float, float, float]:
        classic_h: list[float] = []
        lo_h: list[float] = []
        hi_h: list[float] = []
        p50_h: list[float] = []
        used = regime
        for key in regime_fallback_chain(regime):
            classic_h = self._hist(self._classic, day, key)
            if len(classic_h) >= 5:
                used = key
                lo_h = self._hist(self._lower, day, key)
                hi_h = self._hist(self._upper, day, key)
                p50_h = self._hist(self._p50, day, key)
                break
        _ = used
        classic_m = conformal_quantile(np.asarray(classic_h, float), self.alpha) if len(classic_h) >= 5 else 0.0
        lo_q = conformal_quantile(np.asarray(lo_h, float), self.alpha / 2.0) if len(lo_h) >= 5 else 0.0
        hi_q = conformal_quantile(np.asarray(hi_h, float), self.alpha / 2.0) if len(hi_h) >= 5 else 0.0
        if not np.isfinite(classic_m):
            classic_m = 0.0
        if not np.isfinite(lo_q):
            lo_q = 0.0
        if not np.isfinite(hi_q):
            hi_q = 0.0
        # Never shrink: take the max of classic CQR margin and non-negative asymmetric side
        lo_m = float(max(classic_m, lo_q, 0.0))
        hi_m = float(max(classic_m, hi_q, 0.0))
        if len(p50_h) >= 5:
            p50_shift = conformal_quantile(np.asarray(p50_h, float), self.p50_alpha)
            if not np.isfinite(p50_shift):
                p50_shift = 0.0
        else:
            p50_shift = 0.0
        return lo_m, hi_m, float(p50_shift)

    def calibrate(
        self,
        day: pd.Timestamp,
        pred: dict[float, np.ndarray],
        *,
        regime: str = "all",
        hour_regimes: np.ndarray | None = None,
    ) -> dict[float, np.ndarray]:
        out = {q: np.asarray(v, float).copy() for q, v in pred.items()}
        if 0.10 not in out or 0.90 not in out:
            return out
        if hour_regimes is not None:
            labels = np.asarray([str(x) for x in hour_regimes])
            lo_m = np.zeros(len(out[0.10]))
            hi_m = np.zeros(len(out[0.90]))
            sh = np.zeros(len(out[0.10]))
            for lab in sorted(set(labels)):
                a, b, c = self.margins_for(day, lab)
                mask = labels == lab
                lo_m[mask] = a
                hi_m[mask] = b
                sh[mask] = c
            out[0.10] = out[0.10] - lo_m
            out[0.90] = out[0.90] + hi_m
            if 0.50 in out:
                out[0.50] = out[0.50] + sh
        else:
            lo_m, hi_m, sh = self.margins_for(day, regime)
            out[0.10] = out[0.10] - lo_m
            out[0.90] = out[0.90] + hi_m
            if 0.50 in out:
                out[0.50] = out[0.50] + sh
        if 0.50 in out:
            out[0.50] = np.minimum(np.maximum(out[0.50], out[0.10]), out[0.90])
        else:
            out[0.10] = np.minimum(out[0.10], out[0.90])
        return out

