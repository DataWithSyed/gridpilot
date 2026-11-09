import pytest

from gridpilot_core.battery import BatteryConfig, BatteryState, apply_dispatch


def test_round_trip_loses_to_efficiency():
    cfg = BatteryConfig(
        energy_mwh=2.0,
        power_mw=1.0,
        eta_charge=0.95,
        eta_discharge=0.95,
        soc_min=0.05,
        soc_max=0.95,
        initial_soc=0.5,
    )
    st = BatteryState.from_config(cfg)
    st, gin, _ = apply_dispatch(cfg, st, charge_mw=1.0, discharge_mw=0.0, dt_h=1.0)
    # Headroom to soc_max: (0.95-0.5)*2 / 0.95 ≈ 0.947 MWh grid-in
    assert gin == pytest.approx((0.95 - 0.5) * 2.0 / 0.95)
    assert st.soc == pytest.approx(0.95)
    st2, _, gout = apply_dispatch(cfg, st, charge_mw=0.0, discharge_mw=1.0, dt_h=1.0)
    assert gout > 0
    assert st2.soc < st.soc


def test_soc_ceiling_blocks_charge():
    cfg = BatteryConfig(initial_soc=0.95, soc_max=0.95)
    st = BatteryState.from_config(cfg)
    st2, gin, gout = apply_dispatch(cfg, st, charge_mw=1.0, discharge_mw=0.0)
    assert gin == 0.0
    assert gout == 0.0
    assert st2.soc == pytest.approx(0.95)


def test_rejects_simultaneous():
    cfg = BatteryConfig()
    st = BatteryState.from_config(cfg)
    with pytest.raises(ValueError):
        apply_dispatch(cfg, st, charge_mw=0.5, discharge_mw=0.5)
