"""Risk limits and kill switch for paper trading (no live orders)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskLimits:
    """Hard constraints enforced before any paper fill.

    ASSUMED defaults are conservative portfolio-ops style limits for a 1 MW / 2 MWh
    illustrative BESS; tune per asset.
    """

    max_charge_mw: float | None = None  # None → battery power
    max_discharge_mw: float | None = None
    soc_floor: float | None = None  # None → battery.soc_min
    soc_ceiling: float | None = None  # None → battery.soc_max
    max_cycles_per_day: float = 2.0  # ASSUMED daily cycle budget
    max_drawdown_eur: float = 5_000.0  # peak-to-trough equity stop
    enable_kill_switch: bool = True


@dataclass
class RiskManager:
    limits: RiskLimits
    peak_equity_eur: float = 0.0
    killed: bool = False
    kill_reason: str = ""
    day_cycles: float = 0.0
    _day_key: str | None = None
    blocks: list[str] = field(default_factory=list)

    def reset_day(self, day_key: str) -> None:
        if day_key != self._day_key:
            self._day_key = day_key
            self.day_cycles = 0.0

    def update_equity(self, equity_eur: float) -> None:
        if equity_eur > self.peak_equity_eur:
            self.peak_equity_eur = equity_eur
        dd = self.peak_equity_eur - equity_eur
        if self.limits.enable_kill_switch and dd >= self.limits.max_drawdown_eur:
            self.killed = True
            self.kill_reason = (
                f"drawdown {dd:.2f} EUR >= max_drawdown_eur {self.limits.max_drawdown_eur:.2f}"
            )

    def clip_dispatch(
        self,
        *,
        charge_mw: float,
        discharge_mw: float,
        power_mw: float,
        soc: float,
        soc_min: float,
        soc_max: float,
        energy_mwh: float,
        eta_charge: float,
        eta_discharge: float,
        dt_h: float,
        cycle_increment_if_full: float,
    ) -> tuple[float, float, list[str]]:
        """Clip requested dispatch to risk + physical limits. Returns clipped powers + reasons."""
        reasons: list[str] = []
        if self.killed:
            reasons.append(f"kill_switch:{self.kill_reason}")
            return 0.0, 0.0, reasons

        max_c = self.limits.max_charge_mw if self.limits.max_charge_mw is not None else power_mw
        max_d = self.limits.max_discharge_mw if self.limits.max_discharge_mw is not None else power_mw
        floor = self.limits.soc_floor if self.limits.soc_floor is not None else soc_min
        ceil = self.limits.soc_ceiling if self.limits.soc_ceiling is not None else soc_max

        c = max(0.0, min(charge_mw, max_c, power_mw))
        d = max(0.0, min(discharge_mw, max_d, power_mw))
        if charge_mw > c + 1e-12:
            reasons.append("clipped_charge_power")
        if discharge_mw > d + 1e-12:
            reasons.append("clipped_discharge_power")

        # SoC headroom / floor
        e = soc * energy_mwh
        e_min = floor * energy_mwh
        e_max = ceil * energy_mwh
        if c > 0:
            max_store = max(0.0, (e_max - e) / eta_charge) / dt_h if dt_h > 0 else 0.0
            if c > max_store + 1e-12:
                reasons.append("soc_ceiling")
                c = max(0.0, max_store)
        if d > 0:
            max_draw = max(0.0, (e - e_min) * eta_discharge) / dt_h if dt_h > 0 else 0.0
            if d > max_draw + 1e-12:
                reasons.append("soc_floor")
                d = max(0.0, max_draw)

        # Daily cycle budget (approximate using requested throughput)
        remaining = max(0.0, self.limits.max_cycles_per_day - self.day_cycles)
        # One cycle ≡ 2 * energy_mwh of grid throughput
        max_throughput = remaining * 2.0 * energy_mwh
        req_throughput = (c + d) * dt_h
        if req_throughput > max_throughput + 1e-12:
            reasons.append("max_cycles_per_day")
            scale = max_throughput / req_throughput if req_throughput > 0 else 0.0
            c *= scale
            d *= scale

        if c > 0 and d > 0:
            # Prefer the larger request; zero the other
            if c >= d:
                d = 0.0
            else:
                c = 0.0
            reasons.append("no_simultaneous_charge_discharge")

        # Record intended cycle increment for caller after fill
        _ = cycle_increment_if_full
        self.blocks.extend(reasons)
        return c, d, reasons

    def record_cycles(self, cycle_delta: float) -> None:
        self.day_cycles += cycle_delta
