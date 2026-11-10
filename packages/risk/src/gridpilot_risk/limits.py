"""SoC / cycle / drawdown limit specs and kill-switch hooks for paper trading.

These mirror the semantics of ``gridpilot_core.risk`` so the risk engine can
be used standalone or as a pre-check wrapper. They do **not** place orders.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskLimitSpec:
    max_charge_mw: float | None = None
    max_discharge_mw: float | None = None
    soc_floor: float | None = None
    soc_ceiling: float | None = None
    max_cycles_per_day: float = 2.0  # ASSUMED
    max_drawdown_eur: float = 5_000.0  # ASSUMED
    enable_kill_switch: bool = True


@dataclass
class KillSwitch:
    limits: RiskLimitSpec
    peak_equity_eur: float = 0.0
    killed: bool = False
    reason: str = ""

    def update_equity(self, equity_eur: float) -> bool:
        if equity_eur > self.peak_equity_eur:
            self.peak_equity_eur = equity_eur
        dd = self.peak_equity_eur - equity_eur
        if self.limits.enable_kill_switch and dd >= self.limits.max_drawdown_eur:
            self.killed = True
            self.reason = f"drawdown {dd:.2f} >= {self.limits.max_drawdown_eur:.2f}"
        return self.killed


def enforce_limits(
    *,
    charge_mw: float,
    discharge_mw: float,
    power_mw: float,
    soc: float,
    energy_mwh: float,
    eta_charge: float,
    eta_discharge: float,
    dt_h: float,
    day_cycles: float,
    limits: RiskLimitSpec,
    soc_min: float,
    soc_max: float,
    killed: bool = False,
) -> tuple[float, float, list[str]]:
    """Clip a paper-trading dispatch request to risk + physical limits."""
    reasons: list[str] = []
    if killed:
        return 0.0, 0.0, ["kill_switch"]
    max_c = limits.max_charge_mw if limits.max_charge_mw is not None else power_mw
    max_d = limits.max_discharge_mw if limits.max_discharge_mw is not None else power_mw
    floor = limits.soc_floor if limits.soc_floor is not None else soc_min
    ceil = limits.soc_ceiling if limits.soc_ceiling is not None else soc_max
    c = max(0.0, min(charge_mw, max_c, power_mw))
    d = max(0.0, min(discharge_mw, max_d, power_mw))
    e = soc * energy_mwh
    e_min = floor * energy_mwh
    e_max = ceil * energy_mwh
    if c > 0 and dt_h > 0:
        max_store = max(0.0, (e_max - e) / eta_charge) / dt_h
        if c > max_store:
            reasons.append("soc_ceiling")
            c = max(0.0, max_store)
    if d > 0 and dt_h > 0:
        max_draw = max(0.0, (e - e_min) * eta_discharge) / dt_h
        if d > max_draw:
            reasons.append("soc_floor")
            d = max(0.0, max_draw)
    remaining = max(0.0, limits.max_cycles_per_day - day_cycles)
    max_throughput = remaining * 2.0 * energy_mwh
    req = (c + d) * dt_h
    if req > max_throughput + 1e-12:
        reasons.append("max_cycles_per_day")
        scale = max_throughput / req if req > 0 else 0.0
        c *= scale
        d *= scale
    if c > 0 and d > 0:
        if c >= d:
            d = 0.0
        else:
            c = 0.0
        reasons.append("no_simultaneous_charge_discharge")
    return c, d, reasons
