"""Tests for post-DA re-optimisation and imbalance cash-out (synthetic, no network)."""
from __future__ import annotations

import pandas as pd

from gridpilot_backtest.costs import ZERO_COSTS, ExecutionCosts
from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_forecast.bid_curves import policy_summary, settle_locked_schedule
from gridpilot_forecast.cost_aware_lp import solve_day_lp_with_costs
from gridpilot_forecast.intraday import (
    ID_PRICE_SOURCE,
    REBAP_SOURCE,
    IntradayLayerConfig,
    _id_legs,
    reoptimize_after_da,
)


def _batt(soc: float = 0.20) -> BatteryConfig:
    return BatteryConfig(
        power_mw=1.0, energy_mwh=2.0, degradation_eur_per_mwh=0.0, initial_soc=soc
    )


def test_id_legs_unwind_and_add():
    # DA charged 1, physical discharges 1: sell back the charge and sell the discharge
    buy, sell = _id_legs(1.0, 0.0, 0.0, 1.0)
    assert abs(buy - 0.0) < 1e-12
    assert abs(sell - 2.0) < 1e-12


def test_full_id_close_has_zero_imbalance():
    cfg_b = _batt(0.20)
    idx = pd.date_range("2026-01-05", periods=4, freq="h", tz="Europe/Berlin")
    # Forecast thinks the opposite of realised DA: charge late, discharge early
    p50 = pd.Series([200.0, 180.0, 20.0, 10.0], index=idx)
    realised = pd.Series([10.0, 20.0, 180.0, 200.0], index=idx)
    da_plan = solve_day_lp_with_costs(p50, cfg_b, BatteryState(soc=0.20), ZERO_COSTS)
    layer = IntradayLayerConfig(da_costs=ZERO_COSTS, id_costs=ZERO_COSTS, unfilled_frac=0.0)
    out = reoptimize_after_da(da_plan, realised, cfg_b, 0.20, layer)
    assert out["unfilled_frac"] == 0.0
    assert float(out["actions"]["imb_net_mwh"].abs().sum()) < 1e-9
    # Physical should charge early / discharge late on realised DA
    assert float(out["physical_actions"]["grid_in_mwh"].iloc[0]) > 0.3
    assert float(out["physical_actions"]["grid_out_mwh"].iloc[-1]) > 0.3


def test_reopt_improves_on_a_wrong_forecast_when_id_equals_da():
    cfg_b = _batt(0.20)
    idx = pd.date_range("2026-01-06", periods=4, freq="h", tz="Europe/Berlin")
    p50 = pd.Series([200.0, 180.0, 20.0, 10.0], index=idx)
    realised = pd.Series([10.0, 20.0, 180.0, 200.0], index=idx)
    da_plan = solve_day_lp_with_costs(p50, cfg_b, BatteryState(soc=0.20), ZERO_COSTS)
    da_acts = settle_locked_schedule(da_plan, realised, cfg_b, 0.20)
    da_cash = float(policy_summary(da_acts, ZERO_COSTS)["final_cash_eur"])
    layer = IntradayLayerConfig(da_costs=ZERO_COSTS, id_costs=ZERO_COSTS, unfilled_frac=0.0)
    out = reoptimize_after_da(da_plan, realised, cfg_b, 0.20, layer)
    assert out["final_cash_eur"] > da_cash + 50.0  # wide spread, should be a large lift


def test_unfilled_fraction_creates_imbalance_cashed_at_rebap():
    cfg_b = _batt(0.20)
    idx = pd.date_range("2026-01-07", periods=4, freq="h", tz="Europe/Berlin")
    p50 = pd.Series([200.0, 180.0, 20.0, 10.0], index=idx)
    realised = pd.Series([10.0, 20.0, 180.0, 200.0], index=idx)
    # Provided reBAP is very punitive on longs (high when we would sell extra)
    rebap = pd.Series([-500.0, -500.0, -500.0, -500.0], index=idx)
    da_plan = solve_day_lp_with_costs(p50, cfg_b, BatteryState(soc=0.20), ZERO_COSTS)
    full = reoptimize_after_da(
        da_plan, realised, cfg_b, 0.20,
        IntradayLayerConfig(da_costs=ZERO_COSTS, id_costs=ZERO_COSTS, unfilled_frac=0.0),
    )
    partial = reoptimize_after_da(
        da_plan, realised, cfg_b, 0.20,
        IntradayLayerConfig(da_costs=ZERO_COSTS, id_costs=ZERO_COSTS, unfilled_frac=1.0),
        rebap=rebap,
    )
    assert partial["imb_abs_mwh"] > 0.5
    assert partial["id_throughput_mwh"] < 1e-9
    # Cashing leftover deviations at -500 instead of ID=DA should change cash
    assert abs(partial["final_cash_eur"] - full["final_cash_eur"]) > 1.0
    assert partial["rebap_source"] == "provided_series"


def test_id_fee_is_applied_only_to_id_volume():
    cfg_b = _batt(0.50)
    idx = pd.date_range("2026-01-08", periods=2, freq="h", tz="Europe/Berlin")
    # Forecast already correct so DA plan ≈ physical; little/no ID
    prices = pd.Series([20.0, 200.0], index=idx)
    da_plan = solve_day_lp_with_costs(prices, cfg_b, BatteryState(soc=0.50), ZERO_COSTS)
    id_costs = ExecutionCosts(fee_eur_per_mwh=10.0, slippage_eur_per_mwh=0.0, degradation_eur_per_mwh=0.0)
    out = reoptimize_after_da(
        da_plan, prices, cfg_b, 0.50,
        IntradayLayerConfig(da_costs=ZERO_COSTS, id_costs=id_costs, unfilled_frac=0.0),
    )
    # If the plan is unchanged, ID volume and ID fees are ~0
    assert out["id_throughput_mwh"] < 1e-6
    da_acts = settle_locked_schedule(da_plan, prices, cfg_b, 0.50)
    da_cash = float(policy_summary(da_acts, ZERO_COSTS)["final_cash_eur"])
    assert abs(out["final_cash_eur"] - da_cash) < 1e-6


def test_source_labels_are_proxies_by_default():
    assert ID_PRICE_SOURCE == "proxy_id_eq_da"
    assert REBAP_SOURCE == "proxy_rebap_eq_da"
    cfg = IntradayLayerConfig()
    assert cfg.id_costs.fee_eur_per_mwh == 0.035
