"""BESS state machine: energy/power limits, round-trip efficiency, cycle count."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryConfig:
    """Physical / contractual battery parameters.

    ASSUMED defaults are labelled; override for a specific asset.
    """

    energy_mwh: float = 2.0  # usable energy capacity
    power_mw: float = 1.0  # charge and discharge power rating
    eta_charge: float = 0.95  # ASSUMED one-way charge efficiency
    eta_discharge: float = 0.95  # ASSUMED one-way discharge efficiency
    soc_min: float = 0.05  # ASSUMED residual / reserve SoC
    soc_max: float = 0.95  # ASSUMED top SoC headroom
    initial_soc: float = 0.50
    # Linear degradation cost EUR per MWh-throughput (both ways count). ASSUMED
    # order-of-magnitude from NREL ATB utility BESS O&M / wear proxies; set 0 to disable.
    degradation_eur_per_mwh: float = 5.0

    def __post_init__(self) -> None:
        if self.energy_mwh <= 0 or self.power_mw <= 0:
            raise ValueError("energy_mwh and power_mw must be positive")
        if not (0 < self.eta_charge <= 1 and 0 < self.eta_discharge <= 1):
            raise ValueError("efficiencies must be in (0, 1]")
        if not (0 <= self.soc_min < self.soc_max <= 1):
            raise ValueError("invalid SoC band")
        if not (self.soc_min <= self.initial_soc <= self.soc_max):
            raise ValueError("initial_soc outside [soc_min, soc_max]")


@dataclass
class BatteryState:
    soc: float  # fraction of energy_mwh
    energy_throughput_mwh: float = 0.0  # cumulative |grid energy| for cycles
    cycles: float = 0.0  # throughput / (2 * energy_mwh) equivalent full cycles
    cumulative_degradation_eur: float = 0.0

    @classmethod
    def from_config(cls, cfg: BatteryConfig) -> "BatteryState":
        return cls(soc=cfg.initial_soc)


def apply_dispatch(
    cfg: BatteryConfig,
    state: BatteryState,
    *,
    charge_mw: float,
    discharge_mw: float,
    dt_h: float = 1.0,
) -> tuple[BatteryState, float, float]:
    """Apply one interval of charge/discharge.

    Returns (new_state, grid_import_mwh, grid_export_mwh).
    Positive charge buys from the market; positive discharge sells.
    Both charge_mw and discharge_mw must be >= 0; at most one should be > 0.
    """
    if charge_mw < 0 or discharge_mw < 0:
        raise ValueError("charge_mw and discharge_mw must be non-negative")
    if charge_mw > 0 and discharge_mw > 0:
        raise ValueError("cannot charge and discharge in the same interval")

    charge_mw = min(charge_mw, cfg.power_mw)
    discharge_mw = min(discharge_mw, cfg.power_mw)

    e = state.soc * cfg.energy_mwh
    e_min = cfg.soc_min * cfg.energy_mwh
    e_max = cfg.soc_max * cfg.energy_mwh

    grid_in = 0.0
    grid_out = 0.0

    if charge_mw > 0:
        # Energy stored = grid_in * eta_charge; capped by headroom
        max_store = (e_max - e) / cfg.eta_charge if cfg.eta_charge > 0 else 0.0
        grid_in = min(charge_mw * dt_h, max(0.0, max_store))
        stored = grid_in * cfg.eta_charge
        e = e + stored
    elif discharge_mw > 0:
        # Energy drawn from battery = grid_out / eta_discharge
        max_draw = (e - e_min) * cfg.eta_discharge
        grid_out = min(discharge_mw * dt_h, max(0.0, max_draw))
        drawn = grid_out / cfg.eta_discharge if cfg.eta_discharge > 0 else 0.0
        e = e - drawn

    throughput = grid_in + grid_out
    deg = throughput * cfg.degradation_eur_per_mwh
    new_soc = e / cfg.energy_mwh
    new_cycles = state.cycles + throughput / (2.0 * cfg.energy_mwh)
    new_state = BatteryState(
        soc=new_soc,
        energy_throughput_mwh=state.energy_throughput_mwh + throughput,
        cycles=new_cycles,
        cumulative_degradation_eur=state.cumulative_degradation_eur + deg,
    )
    return new_state, grid_in, grid_out
