import pandas as pd

from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage


def test_perfect_foresight_charges_low_discharges_high():
    idx = pd.date_range("2026-08-01", periods=24, freq="h", tz="Europe/Berlin")
    prices = pd.Series([10.0] * 6 + [50.0] * 12 + [100.0] * 6, index=idx)
    cfg = BatteryConfig(degradation_eur_per_mwh=0.0)
    st = BatteryState.from_config(cfg)
    strat = PerfectForesightDaily()
    d0 = strat.decide(
        ts=idx[0],
        price=10.0,
        history=prices.iloc[:1],
        battery=cfg,
        state=st,
        remaining_day_prices=prices,
    )
    assert d0.charge_mw > 0.5
    # Plan is fixed for the day; discharge should land in the 100 €/MWh block
    evening = [strat._plan[ts].discharge_mw for ts in idx[-6:]]
    morning = [strat._plan[ts].charge_mw for ts in idx[:6]]
    assert sum(evening) > 0.5
    assert sum(morning) > 0.5
    # Re-query last hour should not rebuild into a 1-hour problem
    _ = strat.decide(
        ts=idx[-1],
        price=100.0,
        history=prices,
        battery=cfg,
        state=st,
        remaining_day_prices=prices.iloc[-1:],
    )
    assert strat._plan_day == "2026-08-01"
    assert len(strat._plan) == 24


def test_threshold_warmup_and_hold():
    idx = pd.date_range("2026-08-01", periods=10, freq="h", tz="Europe/Berlin")
    prices = pd.Series(range(10), index=idx, dtype=float)
    cfg = BatteryConfig()
    st = BatteryState.from_config(cfg)
    strat = ThresholdArbitrage(lookback_hours=168)
    d = strat.decide(ts=idx[-1], price=9.0, history=prices, battery=cfg, state=st)
    assert d.note == "warmup"
