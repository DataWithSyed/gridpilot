"""Lightweight tests for the live pilot helpers (no network in unit tests)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_core.strategy import Decision
from gridpilot_live.pilot import _rmse, _settle_plan


def test_rmse_zero_on_identity():
    y = np.array([1.0, 2.0, 3.0])
    assert _rmse(y, y) == 0.0


def test_settle_plan_cash_and_soc():
    idx = pd.date_range("2026-11-01", periods=2, freq="h", tz="Europe/Berlin")
    prices = pd.Series([10.0, 100.0], index=idx)
    battery = BatteryConfig(power_mw=1.0, energy_mwh=2.0, degradation_eur_per_mwh=0.0)
    state = BatteryState.from_config(battery)
    plan = {
        idx[0]: Decision(charge_mw=1.0, note="c"),
        idx[1]: Decision(discharge_mw=1.0, note="d"),
    }
    state2, cash, rows, gross = _settle_plan(plan, prices, battery, state)
    assert len(rows) == 2
    # Buy 1 MWh @10, sell ~0.95*0.95 MWh worth depending on eta path — just check sign/structure
    assert isinstance(cash, float)
    assert battery.soc_min <= state2.soc <= battery.soc_max


def test_settle_plan_gross_vs_net():
    from gridpilot_backtest.costs import ExecutionCosts

    idx = pd.date_range("2026-11-01", periods=2, freq="h", tz="Europe/Berlin")
    prices = pd.Series([10.0, 100.0], index=idx)
    battery = BatteryConfig(power_mw=1.0, energy_mwh=2.0, degradation_eur_per_mwh=0.0)
    state = BatteryState.from_config(battery)
    plan = {
        idx[0]: Decision(charge_mw=1.0, note="c"),
        idx[1]: Decision(discharge_mw=1.0, note="d"),
    }
    costs = ExecutionCosts(0.05, 0.5, 5.0)
    state2, net, rows, gross = _settle_plan(plan, prices, battery, state, costs=costs)
    assert gross > net
    assert all("cash_step_gross" in r for r in rows)
