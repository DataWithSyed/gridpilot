from gridpilot_core.risk import RiskLimits, RiskManager


def test_kill_switch_on_drawdown():
    rm = RiskManager(RiskLimits(max_drawdown_eur=100.0, enable_kill_switch=True))
    rm.update_equity(0.0)
    rm.update_equity(500.0)
    rm.update_equity(350.0)  # dd 150
    assert rm.killed is True


def test_cycle_budget_clips():
    rm = RiskManager(RiskLimits(max_cycles_per_day=0.1))
    rm.reset_day("2026-08-01")
    # 0.1 cycle on 2 MWh battery → 0.4 MWh throughput budget
    c, d, reasons = rm.clip_dispatch(
        charge_mw=1.0,
        discharge_mw=0.0,
        power_mw=1.0,
        soc=0.5,
        soc_min=0.05,
        soc_max=0.95,
        energy_mwh=2.0,
        eta_charge=0.95,
        eta_discharge=0.95,
        dt_h=1.0,
        cycle_increment_if_full=0.0,
    )
    assert "max_cycles_per_day" in reasons
    assert c < 1.0
    assert d == 0.0
