from gridpilot_risk.limits import KillSwitch, RiskLimitSpec, enforce_limits


def test_kill_switch_trips():
    ks = KillSwitch(RiskLimitSpec(max_drawdown_eur=100.0))
    assert ks.update_equity(1000.0) is False
    assert ks.update_equity(950.0) is False
    assert ks.update_equity(890.0) is True
    assert ks.killed


def test_enforce_soc_and_cycles():
    c, d, reasons = enforce_limits(
        charge_mw=1.0,
        discharge_mw=0.0,
        power_mw=1.0,
        soc=0.94,
        energy_mwh=2.0,
        eta_charge=0.95,
        eta_discharge=0.95,
        dt_h=1.0,
        day_cycles=1.9,
        limits=RiskLimitSpec(max_cycles_per_day=2.0, soc_ceiling=0.95),
        soc_min=0.05,
        soc_max=0.95,
    )
    assert c <= 1.0 + 1e-9
    assert d == 0.0
    # near ceiling or cycle budget should clip
    assert c < 1.0 or "soc_ceiling" in reasons or "max_cycles_per_day" in reasons
