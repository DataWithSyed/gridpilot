import pandas as pd

from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_strategies.forecast_lp import ForecastDrivenLP, RiskAwareForecastLP
from gridpilot_strategies.quantile_forecast import RollingQuantilePriceForecast


def _hist(n=24 * 30):
    idx = pd.date_range("2026-08-01", periods=n, freq="h", tz="Europe/Berlin")
    hour = idx.hour
    vals = 100 + 40 * ((hour >= 17) & (hour <= 20)).astype(float) - 20 * ((hour >= 11) & (hour <= 14)).astype(float)
    return pd.Series(vals, index=idx)


def test_quantile_forecast_shape():
    hist = _hist()
    rem = hist.index[-12:]
    fc = RollingQuantilePriceForecast().forecast_day(hist.iloc[:-12], rem)
    assert 0.5 in fc
    assert len(fc[0.5]) == 12


def test_forecast_lp_decide():
    hist = _hist()
    batt = BatteryConfig()
    state = BatteryState.from_config(batt)
    strat = ForecastDrivenLP()
    ts = hist.index[-12]
    remaining = hist.iloc[-12:]
    history = hist.iloc[:-11]  # includes current
    # fix: history should include current bar
    history = hist.loc[:ts]
    remaining = hist.loc[ts:]
    d = strat.decide(ts=ts, price=float(hist.loc[ts]), history=history, battery=batt, state=state, remaining_day_prices=remaining)
    assert d.charge_mw >= 0 and d.discharge_mw >= 0


def test_risk_aware_lp_decide():
    hist = _hist()
    batt = BatteryConfig()
    state = BatteryState.from_config(batt)
    strat = RiskAwareForecastLP()
    ts = hist.index[-8]
    history = hist.loc[:ts]
    remaining = hist.loc[ts : ts.normalize() + pd.Timedelta(hours=23)]
    # ensure remaining within same day
    remaining = hist[(hist.index.date == ts.date()) & (hist.index >= ts)]
    d = strat.decide(ts=ts, price=float(hist.loc[ts]), history=history, battery=batt, state=state, remaining_day_prices=remaining)
    assert isinstance(d.note, str)
