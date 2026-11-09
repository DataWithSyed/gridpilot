"""Unit tests for forecast features, models, fundamentals leakage, conformal."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gridpilot_forecast.conformal import RollingCQR, coverage, reliability_table
from gridpilot_forecast.features import (
    daily_panel,
    gbm_frame_for_day,
    gbm_frame_for_day_with_fundamentals,
    lear_row,
    lear_row_with_fundamentals,
)
from gridpilot_forecast.forecaster import WalkForwardQuantileForecast
from gridpilot_forecast.fundamentals import assert_no_lookahead_price
from gridpilot_forecast.models import EnsembleQuantile, LEARLite, NaiveDayAhead, QuantileGBM, mae


def _synthetic_prices(n_days: int = 40, start: str = "2026-07-01") -> pd.Series:
    idx = pd.date_range(start, periods=n_days * 24, freq="h", tz="Europe/Berlin")
    hour = idx.hour
    vals = 80 + 40 * np.sin((hour - 6) / 24 * 2 * np.pi) + np.random.default_rng(0).normal(0, 5, len(idx))
    return pd.Series(vals, index=idx, name="da")


def _synthetic_fund(n_days: int = 40, start: str = "2026-07-01") -> dict[str, pd.DataFrame]:
    idx = pd.date_range(start, periods=n_days * 24, freq="h", tz="Europe/Berlin")
    hour = idx.hour
    rng = np.random.default_rng(1)
    load = 40000 + 8000 * np.sin((hour - 8) / 24 * 2 * np.pi) + rng.normal(0, 500, len(idx))
    solar = np.clip(15000 * np.sin(np.maximum(hour - 6, 0) / 12 * np.pi), 0, None)
    wind = 8000 + 3000 * rng.normal(0, 1, len(idx)).cumsum() * 0  # stable
    wind = 8000 + 2000 * np.sin(np.arange(len(idx)) / 48)
    df = pd.DataFrame(
        {
            "load_fc": load,
            "solar_fc": solar,
            "wind_onshore_fc": wind * 0.8,
            "wind_offshore_fc": wind * 0.2,
        },
        index=idx,
    )
    from gridpilot_forecast.fundamentals import build_fundamentals_panels

    price = _synthetic_prices(n_days, start)
    full = df.copy()
    full["price"] = price.reindex(df.index).to_numpy()
    return build_fundamentals_panels(full)


def test_daily_panel_shape():
    s = _synthetic_prices(20)
    pan = daily_panel(s)
    assert pan.shape[1] == 24
    assert len(pan) == 20


def test_lear_row_ex_ante():
    s = _synthetic_prices(20)
    pan = daily_panel(s)
    day = pan.index[10]
    x = lear_row(pan, day)
    assert x is not None
    assert x.ndim == 1 and len(x) > 50
    assert lear_row(pan, pan.index[0]) is None


def test_fundamentals_features_ex_ante_no_price_leak():
    """Features for day D must not depend on day D prices (only D-1/D-2/D-7 + D0 forecasts)."""
    s = _synthetic_prices(30)
    pan = daily_panel(s)
    fund = _synthetic_fund(30)
    day = pan.index[15]
    # Mutate day D prices — feature vectors must be unchanged
    f1 = gbm_frame_for_day_with_fundamentals(pan, fund, day)
    x1 = lear_row_with_fundamentals(pan, fund, day)
    pan2 = pan.copy()
    pan2.loc[day] = pan2.loc[day] + 999.0
    f2 = gbm_frame_for_day_with_fundamentals(pan2, fund, day)
    x2 = lear_row_with_fundamentals(pan2, fund, day)
    assert f1 is not None and f2 is not None
    pd.testing.assert_frame_equal(f1, f2)
    np.testing.assert_allclose(x1, x2)
    assert_no_lookahead_price(pan, day, day - pd.Timedelta(days=1))
    with pytest.raises(AssertionError):
        assert_no_lookahead_price(pan, day, day)


def test_naive_mon_uses_d7():
    s = _synthetic_prices(20)
    pan = daily_panel(s)
    mondays = [d for d in pan.index[7:] if d.day_of_week == 0]
    assert mondays
    day = mondays[0]
    pred = NaiveDayAhead().predict_day(pan, day)
    expected = pan.loc[day - pd.Timedelta(days=7)].to_numpy()
    np.testing.assert_allclose(pred, expected)


def test_lear_and_gbm_fit_predict():
    s = _synthetic_prices(50)
    pan = daily_panel(s)
    train = list(pan.index[7:-2])
    lear = LEARLite().fit(pan, train)
    gbm = QuantileGBM().fit(pan, train)
    day = pan.index[-1]
    lp = lear.predict_day(pan, day)
    gp = gbm.predict_day(pan, day)
    assert lp is not None and lp.shape == (24,)
    assert gp is not None and 0.50 in gp and gp[0.50].shape == (24,)
    assert np.all(gp[0.10] <= gp[0.50] + 1e-6)
    assert np.all(gp[0.50] <= gp[0.90] + 1e-6)
    assert mae(lp, pan.loc[day].to_numpy()) < 200


def test_ensemble_with_fundamentals():
    s = _synthetic_prices(50)
    pan = daily_panel(s)
    fund = _synthetic_fund(50)
    ens = EnsembleQuantile(use_fundamentals=True).fit(pan, list(pan.index[7:-2]), fund=fund)
    day = pan.index[-1]
    q = ens.predict_day(pan, day)
    assert q is not None and 0.50 in q


def test_ensemble_and_forecast_day_interface():
    s = _synthetic_prices(50)
    pan = daily_panel(s)
    ens = EnsembleQuantile().fit(pan, list(pan.index[7:-2]))
    day = pan.index[-1]
    q = ens.predict_day(pan, day)
    assert q is not None
    fc = WalkForwardQuantileForecast(lookback_days=28, refit_every_days=7, min_train_days=14, calibrate=False)
    day_tz = pd.Timestamp(day).tz_localize("Europe/Berlin") if day.tzinfo is None else day
    hist = s[s.index <= day_tz + pd.Timedelta(hours=23)]
    rem = pd.date_range(day_tz, periods=24, freq="h", tz="Europe/Berlin")
    out = fc.forecast_day(hist, rem)
    assert set(out) >= {0.10, 0.50, 0.90}
    assert len(out[0.50]) == 24


def test_conformal_improves_or_reports_coverage():
    rng = np.random.default_rng(0)
    y = rng.normal(100, 20, size=500)
    # Badly under-dispersed intervals
    lo = y * 0 + 90
    hi = y * 0 + 110
    raw_cov = coverage(y, lo, hi)
    cqr = RollingCQR(alpha=0.2, window_days=30, delay=1)
    # Feed first 200 as history in blocks of 24
    for i in range(0, 200, 24):
        cqr.observe_day(pd.Timestamp("2026-01-01") + pd.Timedelta(days=i // 24), y[i : i + 24], lo[i : i + 24], hi[i : i + 24])
    day = pd.Timestamp("2026-01-01") + pd.Timedelta(days=10)
    pred = cqr.calibrate(day, {0.10: lo[200:224].copy(), 0.50: y[200:224] * 0 + 100, 0.90: hi[200:224].copy()})
    # Margin should be non-negative when undercoverage dominates
    assert pred[0.90].mean() >= hi[200:224].mean() - 1e-6 or pred[0.10].mean() <= lo[200:224].mean() + 1e-6
    rel = reliability_table(y[:200], {0.10: lo[:200], 0.50: np.full(200, 100.0), 0.90: hi[:200]})
    assert 0.10 in rel and 0.90 in rel
    assert raw_cov >= 0.0  # smoke
