"""Unit tests for forecast features and models (no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gridpilot_forecast.features import daily_panel, gbm_frame_for_day, lear_row
from gridpilot_forecast.forecaster import WalkForwardQuantileForecast
from gridpilot_forecast.models import EnsembleQuantile, LEARLite, NaiveDayAhead, QuantileGBM, mae


def _synthetic_prices(n_days: int = 40, start: str = "2026-07-01") -> pd.Series:
    idx = pd.date_range(start, periods=n_days * 24, freq="h", tz="Europe/Berlin")
    hour = idx.hour
    # Diurnal shape + noise
    vals = 80 + 40 * np.sin((hour - 6) / 24 * 2 * np.pi) + np.random.default_rng(0).normal(0, 5, len(idx))
    return pd.Series(vals, index=idx, name="da")


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
    # Missing lag -> None
    assert lear_row(pan, pan.index[0]) is None


def test_naive_mon_uses_d7():
    s = _synthetic_prices(20)
    pan = daily_panel(s)
    # Find a Monday with lag available
    mondays = [d for d in pan.index[7:] if d.dayofweek == 0]
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
    # MAE finite vs truth
    assert mae(lp, pan.loc[day].to_numpy()) < 200


def test_ensemble_and_forecast_day_interface():
    s = _synthetic_prices(50)
    pan = daily_panel(s)
    ens = EnsembleQuantile().fit(pan, list(pan.index[7:-2]))
    day = pan.index[-1]
    q = ens.predict_day(pan, day)
    assert q is not None
    fc = WalkForwardQuantileForecast(lookback_days=28, refit_every_days=7, min_train_days=14)
    # history up to end of delivery day (agent grows history within the day)
    day_tz = pd.Timestamp(day).tz_localize("Europe/Berlin") if day.tzinfo is None else day
    hist = s[s.index <= day_tz + pd.Timedelta(hours=23)]
    rem = pd.date_range(day_tz, periods=24, freq="h", tz="Europe/Berlin")
    out = fc.forecast_day(hist, rem)
    assert set(out) >= {0.10, 0.50, 0.90}
    assert len(out[0.50]) == 24
