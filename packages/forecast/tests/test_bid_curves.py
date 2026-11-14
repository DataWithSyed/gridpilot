"""Unit tests for SDAC-style gate-closure bid curves (synthetic, no network)."""
from __future__ import annotations

import pandas as pd

from gridpilot_backtest.costs import ExecutionCosts, SOURCED_COSTS, ZERO_COSTS
from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_forecast.bid_curves import (
    GATE_CLOSURE_HOUR,
    MARGINAL_ACCEPT_FRACTION,
    build_quantile_bid_curve,
    build_curves_for_day,
    build_water_value_bid_curve,
    clear_day_curves,
    evaluate_day,
    gate_closure_time,
    reservation_prices,
    rolling_hod_quantiles,
    settle_locked_schedule,
)
from gridpilot_core.strategy import Decision
from gridpilot_forecast.cost_aware_lp import cycle_addend_eur_per_mwh, solve_day_lp_with_costs, water_value_on_path


def _batt(*, soc: float = 0.50) -> tuple[BatteryConfig, BatteryState]:
    cfg = BatteryConfig(
        power_mw=1.0,
        energy_mwh=2.0,
        degradation_eur_per_mwh=0.0,
        initial_soc=soc,
    )
    return cfg, BatteryState.from_config(cfg)


def test_gate_closure_is_noon_berlin_d_minus_1():
    ts = pd.Timestamp("2026-03-15 07:00", tz="Europe/Berlin")
    gc = gate_closure_time(ts)
    assert str(gc.tz) == "Europe/Berlin"
    assert gc.hour == GATE_CLOSURE_HOUR
    assert gc.minute == 0
    assert gc.date().isoformat() == "2026-03-14"


def test_buy_fully_accepted_when_price_below_all_limits():
    costs = ExecutionCosts(0.015, 0.0, 5.0, label="sourced")
    curve = build_quantile_bid_curve(
        ts=pd.Timestamp("2026-01-01", tz="Europe/Berlin"),
        p10=40.0, p50=50.0, p90=80.0, power_mw=1.0, costs=costs,
    )
    add = cycle_addend_eur_per_mwh(costs)
    # lowest buy limit is p10 - add; go well below it
    ch, dis = curve.accepted_volume(40.0 - add - 10.0)
    assert ch == 1.0
    assert dis == 0.0
    assert max(s.limit_eur_mwh for s in curve.buy_steps) < min(s.limit_eur_mwh for s in curve.sell_steps)


def test_buy_rejected_when_price_above_all_limits():
    costs = ExecutionCosts(0.015, 0.0, 5.0, label="sourced")
    curve = build_quantile_bid_curve(
        ts=pd.Timestamp("2026-01-01", tz="Europe/Berlin"),
        p10=40.0, p50=50.0, p90=80.0, power_mw=1.0, costs=costs,
    )
    ch, dis = curve.accepted_volume(1_000.0)
    assert ch == 0.0
    # 1000 is above p90 + add, so sell is fully accepted
    assert dis == 1.0


def test_sell_rejected_when_price_below_offers():
    costs = ExecutionCosts(0.015, 0.0, 5.0, label="sourced")
    curve = build_quantile_bid_curve(
        ts=pd.Timestamp("2026-01-01", tz="Europe/Berlin"),
        p10=40.0, p50=50.0, p90=80.0, power_mw=1.0, costs=costs,
    )
    add = cycle_addend_eur_per_mwh(costs)
    ch, dis = curve.accepted_volume(50.0)  # around mid; buy may clear, sell should not
    # sell min is p50 + add > 50
    assert dis == 0.0
    assert min(s.limit_eur_mwh for s in curve.sell_steps) == 50.0 + add or min(
        s.limit_eur_mwh for s in curve.sell_steps
    ) >= 50.0 + add - 1e-9


def test_partial_acceptance_at_clearing_price_tie():
    costs = ZERO_COSTS
    # p10 = p50 so the three buy steps merge to one full-power step at p50 - 0.01 (gap)
    curve = build_quantile_bid_curve(
        ts=pd.Timestamp("2026-01-01", tz="Europe/Berlin"),
        p10=50.0, p50=50.0, p90=50.0, power_mw=1.0, costs=costs, n_steps=1,
    )
    assert len(curve.buy_steps) == 1
    limit = curve.buy_steps[0].limit_eur_mwh
    ch, dis = curve.accepted_volume(limit)
    assert abs(ch - MARGINAL_ACCEPT_FRACTION * 1.0) < 1e-9
    assert dis == 0.0


def test_soc_partial_acceptance_caps_charge():
    cfg, _ = _batt(soc=0.95)  # already at soc_max, no headroom
    idx = pd.date_range("2026-01-01", periods=1, freq="h", tz="Europe/Berlin")
    prices = pd.Series([-50.0], index=idx)
    p10 = p50 = p90 = pd.Series([100.0], index=idx)  # forecast thinks expensive; realised is cheap
    # Force a buy: use a high forecast mid so buy limit is still above -50? 
    # buy limit ~ p50 - add. p50=100, realised -50, full buy requested, SoC clips to 0.
    costs = ZERO_COSTS
    curves = build_curves_for_day(p10, p50, p90, cfg.power_mw, costs)
    df = clear_day_curves(curves, prices, cfg, soc=0.95)
    assert float(df["grid_in_mwh"].iloc[0]) < 1e-9
    assert "soc_partial" in str(df["note"].iloc[0]) or float(df["charge_mw"].iloc[0]) == 0.0
    assert cfg.soc_min - 1e-9 <= float(df["soc"].iloc[0]) <= cfg.soc_max + 1e-9


def test_no_simultaneous_charge_and_discharge_and_soc_band():
    cfg, _ = _batt(soc=0.50)
    idx = pd.date_range("2026-01-02", periods=24, freq="h", tz="Europe/Berlin")
    prices = pd.Series([20.0 if h < 12 else 180.0 for h in range(24)], index=idx)
    p10 = prices * 0.8
    p50 = prices.copy()
    p90 = prices * 1.2
    ev = evaluate_day(
        prices, p10, p50, p90, cfg, SOURCED_COSTS,
        soc_schedule=0.50, soc_quantile=0.50, soc_anchored=0.50,
    )
    for name, df in ev.items():
        if name in {"plan", "water_values"}:
            continue
        both = (df["charge_mw"] > 1e-9) & (df["discharge_mw"] > 1e-9)
        assert not bool(both.any()), name
        assert (df["soc"] >= cfg.soc_min - 1e-9).all()
        assert (df["soc"] <= cfg.soc_max + 1e-9).all()


def test_hod_quantiles_are_causal():
    idx = pd.date_range("2026-01-01", periods=48, freq="h", tz="Europe/Berlin")
    hist = pd.Series(50.0, index=idx)
    # Spike only on day 2 — must not leak into day-2 forecast built at gate closure
    hist.iloc[24:] = 999.0
    day2 = idx[24:]
    fans = rolling_hod_quantiles(hist, day2, lookback_days=90)
    # history used is strictly before 2026-01-02 00:00, so all quantiles stay at 50
    assert (fans[0.50] == 50.0).all()
    assert (fans[0.10] == 50.0).all()
    assert (fans[0.90] == 50.0).all()


def test_bids_skip_unprofitable_locked_charge():
    """If the realised price is far above the forecast, bids should not fill a charge the schedule still takes."""
    cfg, _ = _batt(soc=0.20)
    idx = pd.date_range("2026-01-03", periods=4, freq="h", tz="Europe/Berlin")
    # Forecast: cheap then expensive — schedule will charge hour 0, discharge hour 3
    p10 = pd.Series([10.0, 12.0, 80.0, 90.0], index=idx)
    p50 = pd.Series([20.0, 22.0, 100.0, 120.0], index=idx)
    p90 = pd.Series([30.0, 32.0, 130.0, 150.0], index=idx)
    # Realised: hour 0 is actually very expensive (forecast miss)
    prices = pd.Series([200.0, 22.0, 100.0, 120.0], index=idx)
    ev = evaluate_day(
        prices, p10, p50, p90, cfg, ZERO_COSTS,
        soc_schedule=0.20, soc_quantile=0.20, soc_anchored=0.20,
    )
    sched_ch = float(ev["schedule"]["grid_in_mwh"].iloc[0])
    bid_ch = float(ev["quantile_bid"]["grid_in_mwh"].iloc[0])
    assert sched_ch > 0.1, "schedule should still charge on the P50 plan"
    assert bid_ch < 1e-9, "quantile bids should reject a 200 €/MWh fill against ~20 limits"


def test_negative_prices_charge():
    costs = ZERO_COSTS
    curve = build_quantile_bid_curve(
        ts=pd.Timestamp("2026-01-01", tz="Europe/Berlin"),
        p10=-30.0, p50=-10.0, p90=20.0, power_mw=1.0, costs=costs,
    )
    ch, dis = curve.accepted_volume(-40.0)
    assert ch > 0.5
    assert dis == 0.0


def test_locked_schedule_matches_lp_volume_when_soc_allows():
    cfg, st = _batt(soc=0.50)
    idx = pd.date_range("2026-01-04", periods=4, freq="h", tz="Europe/Berlin")
    prices = pd.Series([10.0, 11.0, 200.0, 210.0], index=idx)
    plan = solve_day_lp_with_costs(prices, cfg, st, ZERO_COSTS)
    df = settle_locked_schedule(plan, prices, cfg, 0.50)
    assert float(df["grid_in_mwh"].sum()) > 0.5
    assert float(df["grid_out_mwh"].sum()) > 0.4



def _eta1_batt(**kw) -> BatteryConfig:
    defaults = dict(
        power_mw=1.0,
        energy_mwh=2.0,
        eta_charge=1.0,
        eta_discharge=1.0,
        soc_min=0.0,
        soc_max=1.0,
        initial_soc=0.20,
        degradation_eur_per_mwh=0.0,
    )
    defaults.update(kw)
    return BatteryConfig(**defaults)


def test_two_hour_finite_difference_water_value_equals_sale_price():
    """With unit efficiency, no addend, and headroom to sell, wv equals the remaining sale price."""
    cfg = _eta1_batt(initial_soc=0.20)
    idx = pd.date_range("2026-01-05", periods=2, freq="h", tz="Europe/Berlin")
    prices = pd.Series([100.0, 100.0], index=idx)
    wv = water_value_on_path(prices, cfg, soc0=0.20, costs=ZERO_COSTS, soc_delta=0.02)
    assert abs(float(wv.iloc[0]) - 100.0) < 1.5
    # No terminal value after the last hour, so the last-hour water value is 0
    # and a sale is reserved at the cycle addend only.
    assert abs(float(wv.iloc[1]) - 0.0) < 1.5
    buy, sell = reservation_prices(float(wv.iloc[0]), cfg, ZERO_COSTS)
    assert abs(buy - 100.0) < 1.5
    assert abs(sell - 100.0) < 1.5


def test_water_value_holds_through_shoulder_for_evening_peak():
    """Myopic P50 curves sell in an 80 €/MWh shoulder; water-value reservations wait for 150."""
    cfg = _eta1_batt(initial_soc=0.0)
    idx = pd.date_range("2026-01-06", periods=5, freq="h", tz="Europe/Berlin")
    # Two cheap hours fill the 2 MWh battery; one shoulder; two peak hours that
    # exactly exhaust inventory. There is no later recharge, so a shoulder sale
    # would steal a 150 €/MWh peak sale. Realised cheap/peak are strictly inside
    # the buy / sell regions so a knife-edge π == reservation does not miss the fill.
    p50 = pd.Series([20.0, 20.0, 80.0, 150.0, 150.0], index=idx)
    p10 = p50 - 5.0
    p90 = p50 + 5.0
    prices = pd.Series([10.0, 10.0, 90.0, 160.0, 160.0], index=idx)
    ev = evaluate_day(
        prices, p10, p50, p90, cfg, ZERO_COSTS,
        soc_schedule=0.0, soc_quantile=0.0, soc_anchored=0.0, soc_water=0.0,
    )
    wv_acts = ev["water_value_bid"]
    shoulder = wv_acts.iloc[2:3]
    peak = wv_acts.iloc[3:]
    q_shoulder = ev["quantile_bid"].iloc[2:3]
    assert float(wv_acts["grid_in_mwh"].iloc[:2].sum()) > 0.5, "should fill in the cheap hours"
    assert float(shoulder["grid_out_mwh"].sum()) < 1e-9, "water-value bids should hold through the shoulder"
    assert float(peak["grid_out_mwh"].sum()) > 0.4, "water-value bids should sell into the evening peak"
    assert float(q_shoulder["grid_out_mwh"].sum()) > 0.5, "myopic quantile bids should sell the shoulder"
    mid_wv = float(ev["water_values"].iloc[2])
    assert mid_wv > 120.0, mid_wv


def test_water_value_curve_centres_on_reservation_not_p50():
    cfg = _eta1_batt()
    ts = pd.Timestamp("2026-01-07", tz="Europe/Berlin")
    curve = build_water_value_bid_curve(
        ts=ts, p10=70.0, p50=80.0, p90=90.0,
        water_value_eur_mwh=150.0, battery=cfg, costs=ZERO_COSTS,
    )
    # Stored energy is worth 150, so 80 is a buy (below reservation) not a sell.
    ch, dis = curve.accepted_volume(80.0)
    assert ch > 0.5
    assert dis == 0.0
    assert min(s.limit_eur_mwh for s in curve.sell_steps) >= 150.0 - 1e-9
    ch2, dis2 = curve.accepted_volume(160.0)
    assert ch2 == 0.0
    assert dis2 > 0.5
