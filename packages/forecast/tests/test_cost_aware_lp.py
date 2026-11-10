"""Cost-aware LP unit tests (synthetic, no network)."""
from __future__ import annotations

import pandas as pd

from gridpilot_backtest.costs import ExecutionCosts, ZERO_COSTS
from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_forecast.cost_aware_lp import cycle_addend_eur_per_mwh, solve_day_lp_with_costs


def _empty_batt():
    # Start at soc_min so any discharge must be pre-charged in-window
    cfg = BatteryConfig(
        power_mw=1.0, energy_mwh=2.0, degradation_eur_per_mwh=0.0, initial_soc=0.05
    )
    return cfg, BatteryState.from_config(cfg)


def test_high_costs_skip_thin_spread():
    cfg, state = _empty_batt()
    idx = pd.date_range("2026-01-01", periods=2, freq="h", tz="Europe/Berlin")
    prices = pd.Series([80.0, 100.0], index=idx)  # 20 € spread, add=35 each way
    heavy = ExecutionCosts(fee_eur_per_mwh=5.0, slippage_eur_per_mwh=10.0, degradation_eur_per_mwh=20.0)
    plan = solve_day_lp_with_costs(prices, cfg, state, heavy)
    assert plan[idx[0]].charge_mw < 1e-6
    assert plan[idx[1]].discharge_mw < 1e-6


def test_zero_costs_cycle_wide_spread():
    cfg, state = _empty_batt()
    idx = pd.date_range("2026-01-01", periods=2, freq="h", tz="Europe/Berlin")
    prices = pd.Series([20.0, 200.0], index=idx)
    plan = solve_day_lp_with_costs(prices, cfg, state, ZERO_COSTS)
    assert plan[idx[0]].charge_mw > 0.5
    assert plan[idx[1]].discharge_mw > 0.4


def test_cycle_addend():
    c = ExecutionCosts(0.05, 0.5, 5.0)
    assert cycle_addend_eur_per_mwh(c) == 5.55
