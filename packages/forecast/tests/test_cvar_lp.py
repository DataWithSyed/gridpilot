"""Tests for the cost-aware CVaR LP (synthetic, no network)."""
from __future__ import annotations

import pandas as pd

from gridpilot_backtest.costs import SOURCED_COSTS, ZERO_COSTS
from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_forecast.cost_aware_lp import solve_day_lp_with_costs
from gridpilot_forecast.cvar_lp import (
    historical_day_scenarios,
    in_sample_expected_cash,
    solve_day_lp_cvar,
)


def _batt(soc: float = 0.20) -> BatteryConfig:
    return BatteryConfig(
        power_mw=1.0, energy_mwh=2.0, degradation_eur_per_mwh=0.0, initial_soc=soc
    )


def test_lambda_zero_matches_cost_aware_lp_on_one_scenario():
    cfg = _batt(0.20)
    st = BatteryState(soc=0.20)
    idx = pd.date_range("2026-02-01", periods=4, freq="h", tz="Europe/Berlin")
    path = pd.Series([10.0, 15.0, 180.0, 200.0], index=idx)
    ev = solve_day_lp_cvar([path], cfg, st, ZERO_COSTS, lam=0.0, alpha=0.05)
    ca = solve_day_lp_with_costs(path, cfg, st, ZERO_COSTS)
    for ts in idx:
        assert abs(ev[ts].charge_mw - ca[ts].charge_mw) < 1e-4
        assert abs(ev[ts].discharge_mw - ca[ts].discharge_mw) < 1e-4


def test_high_lambda_avoids_tail_loss_cycle():
    cfg = _batt(0.20)
    st = BatteryState(soc=0.20)
    idx = pd.date_range("2026-02-02", periods=2, freq="h", tz="Europe/Berlin")
    # 19 benign scenarios: cheap then expensive. One disaster: hour-1 price collapses.
    benign = pd.Series([20.0, 200.0], index=idx)
    disaster = pd.Series([20.0, -400.0], index=idx)
    scenarios = [benign] * 19 + [disaster]
    ev = solve_day_lp_cvar(scenarios, cfg, st, ZERO_COSTS, lam=0.0, alpha=0.05)
    tight = solve_day_lp_cvar(scenarios, cfg, st, ZERO_COSTS, lam=10.0, alpha=0.05)
    # EV should still cycle (19/20 paths are juicy)
    assert ev[idx[0]].charge_mw > 0.3
    assert ev[idx[1]].discharge_mw > 0.3
    # High CVaR penalty should shrink or skip the discharge into the tail
    ev_cash = in_sample_expected_cash(ev, scenarios, ZERO_COSTS)
    tight_cash = in_sample_expected_cash(tight, scenarios, ZERO_COSTS)
    assert tight_cash <= ev_cash + 1e-6
    assert tight[idx[1]].discharge_mw < ev[idx[1]].discharge_mw - 0.1


def test_historical_scenarios_are_causal():
    idx = pd.date_range("2026-01-01", periods=72, freq="h", tz="Europe/Berlin")
    hist = pd.Series(50.0, index=idx)
    hist.iloc[48:] = 999.0  # day 3 spike must not leak into day-3 scenarios
    day3 = idx[48:]
    sc = historical_day_scenarios(hist, day3, n_days=60)
    assert len(sc) == 2  # only day 1 and day 2
    for s in sc:
        assert (s == 50.0).all()


def test_sourced_costs_are_accepted():
    cfg = _batt(0.50)
    st = BatteryState(soc=0.50)
    idx = pd.date_range("2026-02-03", periods=2, freq="h", tz="Europe/Berlin")
    path = pd.Series([20.0, 200.0], index=idx)
    plan = solve_day_lp_cvar([path], cfg, st, SOURCED_COSTS, lam=1.0)
    # From SoC 0.50 only a top-up charge is needed before a 1 MW discharge
    assert plan[idx[0]].charge_mw > 0.05
    assert plan[idx[1]].discharge_mw > 0.5
