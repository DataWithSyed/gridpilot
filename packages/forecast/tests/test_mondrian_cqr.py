"""Mondrian asymmetric CQR unit tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from gridpilot_forecast.conformal import (
    MondrianAsymmetricCQR,
    coverage,
    hour_bucket,
    residual_load_regime,
)


def test_residual_load_regime_and_hour_bucket():
    assert residual_load_regime(-10, (0.0, 10.0)) == "low"
    assert residual_load_regime(5, (0.0, 10.0)) == "mid"
    assert residual_load_regime(20, (0.0, 10.0)) == "high"
    assert hour_bucket(3) == "night"
    assert hour_bucket(12) == "day"


def test_mondrian_widens_underdispersed_bands():
    rng = np.random.default_rng(1)
    cqr = MondrianAsymmetricCQR(alpha=0.2, window_days=40, delay=1)
    # Feed 30 days of under-dispersed intervals
    for i in range(30):
        day = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        y = rng.normal(100, 25, size=24)
        lo = np.full(24, 90.0)
        hi = np.full(24, 110.0)
        p50 = np.full(24, 100.0)
        reg = "low" if i % 2 == 0 else "high"
        cqr.observe_day(day, y, lo, hi, regime=reg, q_p50=p50)
    day = pd.Timestamp("2026-02-05")
    pred = {0.10: np.full(24, 90.0), 0.50: np.full(24, 98.0), 0.90: np.full(24, 110.0)}
    cal = cqr.calibrate(day, pred, regime="low")
    # Expect wider band after calibration
    assert float(np.mean(cal[0.90] - cal[0.10])) >= float(np.mean(pred[0.90] - pred[0.10])) - 1e-9
    # Synthetic coverage smoke
    y = rng.normal(100, 20, size=200)
    assert coverage(y, y - 50, y + 50) > 0.9
