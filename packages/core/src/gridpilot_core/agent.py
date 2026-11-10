"""Paper-trading agent loop (never places real market orders)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from gridpilot_core.battery import BatteryConfig, BatteryState, apply_dispatch
from gridpilot_core.events import EventLog
from gridpilot_core.risk import RiskLimits, RiskManager
from gridpilot_core.risk_stats import daily_pnl, rolling_pnl_percentiles, summary_distribution
from gridpilot_core.strategy import Decision, Strategy


@dataclass
class AgentResult:
    equity_eur: pd.Series
    soc: pd.Series
    actions: pd.DataFrame
    events: EventLog
    summary: dict[str, Any] = field(default_factory=dict)
    daily: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    rolling_pct: pd.DataFrame = field(default_factory=pd.DataFrame)


class PaperAgent:
    """Causal (or oracle, if strategy uses foresight) paper-trading simulator."""

    def __init__(
        self,
        battery: BatteryConfig,
        strategy: Strategy,
        risk: RiskLimits | None = None,
        *,
        dt_h: float = 1.0,
        initial_cash_eur: float = 0.0,
    ) -> None:
        self.battery = battery
        self.strategy = strategy
        self.risk_limits = risk or RiskLimits()
        self.dt_h = dt_h
        self.initial_cash_eur = initial_cash_eur

    def run(self, prices: pd.Series) -> AgentResult:
        prices = prices.dropna().astype(float).sort_index()
        if prices.empty:
            raise ValueError("prices series is empty")

        state = BatteryState.from_config(self.battery)
        risk = RiskManager(self.risk_limits)
        log = EventLog()
        cash = self.initial_cash_eur
        equity_rows: list[tuple[Any, float]] = []
        soc_rows: list[tuple[Any, float]] = []
        action_rows: list[dict[str, Any]] = []

        # Pre-index by Berlin calendar day for perfect-foresight day slices
        berlin = prices.copy()
        if berlin.index.tz is None:
            berlin.index = berlin.index.tz_localize("Europe/Berlin")
        else:
            berlin.index = berlin.index.tz_convert("Europe/Berlin")

        history_vals: list[float] = []
        history_idx: list[Any] = []

        for ts, price in berlin.items():
            day_key = str(ts.date())
            risk.reset_day(day_key)
            risk.update_equity(cash)
            if risk.killed:
                log.emit(ts, "kill_switch", reason=risk.kill_reason, cash=cash)
                equity_rows.append((ts, cash))
                soc_rows.append((ts, state.soc))
                action_rows.append(
                    {
                        "ts": ts,
                        "price": price,
                        "charge_mw": 0.0,
                        "discharge_mw": 0.0,
                        "cash": cash,
                        "soc": state.soc,
                        "note": "killed",
                    }
                )
                continue

            history_idx.append(ts)
            history_vals.append(float(price))
            history = pd.Series(history_vals, index=pd.DatetimeIndex(history_idx))

            # Remaining prices for this calendar day (includes current) — foresight strategies only
            day_mask = berlin.index.date == ts.date()
            day_prices = berlin.loc[day_mask]
            remaining = day_prices.loc[ts:]

            decision: Decision = self.strategy.decide(
                ts=ts,
                price=float(price),
                history=history,
                battery=self.battery,
                state=state,
                remaining_day_prices=remaining,
            )
            log.emit(
                ts,
                "decision",
                charge_mw=decision.charge_mw,
                discharge_mw=decision.discharge_mw,
                note=decision.note,
            )

            cycles_before = state.cycles
            c, d, reasons = risk.clip_dispatch(
                charge_mw=decision.charge_mw,
                discharge_mw=decision.discharge_mw,
                power_mw=self.battery.power_mw,
                soc=state.soc,
                soc_min=self.battery.soc_min,
                soc_max=self.battery.soc_max,
                energy_mwh=self.battery.energy_mwh,
                eta_charge=self.battery.eta_charge,
                eta_discharge=self.battery.eta_discharge,
                dt_h=self.dt_h,
                cycle_increment_if_full=0.0,
            )
            if reasons:
                log.emit(ts, "risk_block", reasons=";".join(reasons), req_c=decision.charge_mw, req_d=decision.discharge_mw)

            state, grid_in, grid_out = apply_dispatch(
                self.battery, state, charge_mw=c, discharge_mw=d, dt_h=self.dt_h
            )
            # Cash: buy at price (charge), sell at price (discharge); subtract degradation
            cash -= grid_in * float(price)
            cash += grid_out * float(price)
            # Degradation already accumulated on state; reflect in cash
            # (apply_dispatch added deg to state; charge cash for the increment)
            # Recompute increment:
            # Actually apply_dispatch added to cumulative; track via cycles delta
            cycle_delta = state.cycles - cycles_before
            risk.record_cycles(cycle_delta)
            # Pay degradation for this step
            step_throughput = grid_in + grid_out
            cash -= step_throughput * self.battery.degradation_eur_per_mwh

            log.emit(
                ts,
                "fill",
                grid_in_mwh=grid_in,
                grid_out_mwh=grid_out,
                price=float(price),
                cash=cash,
                soc=state.soc,
            )
            equity_rows.append((ts, cash))
            soc_rows.append((ts, state.soc))
            action_rows.append(
                {
                    "ts": ts,
                    "price": float(price),
                    "charge_mw": c,
                    "discharge_mw": d,
                    "grid_in_mwh": grid_in,
                    "grid_out_mwh": grid_out,
                    "cash": cash,
                    "soc": state.soc,
                    "note": decision.note,
                    "risk": ";".join(reasons),
                }
            )

        equity = pd.Series({t: v for t, v in equity_rows}).rename("equity_eur")
        soc = pd.Series({t: v for t, v in soc_rows}).rename("soc")
        actions = pd.DataFrame(action_rows)
        daily = daily_pnl(equity)
        rolling = rolling_pnl_percentiles(daily, window=7)
        dist = summary_distribution(daily)
        summary = {
            "strategy": getattr(self.strategy, "name", type(self.strategy).__name__),
            "n_hours": int(len(berlin)),
            "final_cash_eur": float(cash),
            "final_soc": float(state.soc),
            "total_cycles": float(state.cycles),
            "killed": bool(risk.killed),
            "kill_reason": risk.kill_reason,
            "daily_pnl_mean_eur": dist["mean"],
            "daily_pnl_p10_eur": dist["p10"],
            "daily_pnl_p50_eur": dist["p50"],
            "daily_pnl_p90_eur": dist["p90"],
            "n_days_pnl": dist["n_days"],
            "price_mean_eur_mwh": float(berlin.mean()),
            "price_min_eur_mwh": float(berlin.min()),
            "price_max_eur_mwh": float(berlin.max()),
        }
        return AgentResult(
            equity_eur=equity,
            soc=soc,
            actions=actions,
            events=log,
            summary=summary,
            daily=daily,
            rolling_pct=rolling,
        )
