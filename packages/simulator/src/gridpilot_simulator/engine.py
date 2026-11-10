"""No-lookahead paper replay engine.

At each tick the agent sees only information that would have been available
then. Day-ahead schedules for delivery day D are locked at 12:00 Europe/Berlin
on D-1 (gate closure) using a forecast built on history strictly before that
instant. Realised DA prices for day D are used only at settlement, never as
inputs to that day's schedule. Perfect-foresight is computed only as a labelled
oracle baseline.

Paper trading only — this module never places or routes real orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from gridpilot_backtest.costs import SOURCED_COSTS, ExecutionCosts, apply_costs_to_actions
from gridpilot_core.battery import BatteryConfig, BatteryState, apply_dispatch
from gridpilot_core.risk import RiskLimits, RiskManager
from gridpilot_core.strategy import Decision, ThresholdArbitrage
from gridpilot_forecast.cost_aware_lp import solve_day_lp_with_costs
from gridpilot_forecast.bid_curves import build_curves_for_day
from gridpilot_forecast.cvar_lp import historical_day_scenarios, solve_day_lp_cvar
from gridpilot_forecast.intraday import IntradayLayerConfig, reoptimize_after_da
from gridpilot_simulator.clock import (
    SimClock,
    as_berlin,
    delivery_day,
    gate_closure_for,
    is_da_publication_tick,
    is_gate_closure_tick,
)
from gridpilot_simulator.scenarios import Scenario

POLICIES = ("cost_aware", "quantile_bids", "cvar", "id_reopt")

# Match the paper 1 MW / 2 MWh agent used in backtests.
DEFAULT_DRAWDOWN_EUR = 20_000.0
DEFAULT_CYCLES_PER_DAY = 2.0


def _hour_climatology(history: pd.Series, hours: pd.DatetimeIndex, bias: float = 0.0) -> pd.DataFrame:
    """P10/P50/P90 from hour-of-day residuals. Uses *history only* (no lookahead)."""
    hist = history.dropna()
    if hist.empty:
        p50 = pd.Series(0.0, index=hours)
        return pd.DataFrame({"p10": p50 - 10, "p50": p50, "p90": p50 + 10})
    h = hist.copy()
    h.index = pd.DatetimeIndex(h.index)
    by_hour = h.groupby(h.index.tz_convert("Europe/Berlin").hour if h.index.tz is not None else h.index.hour)
    p50_map = by_hour.median()
    resid = h - h.index.map(lambda t: float(p50_map.get(as_berlin(t).hour, h.median())))
    lo = float(np.nanquantile(resid.to_numpy(float), 0.10)) if len(resid) else -10.0
    hi = float(np.nanquantile(resid.to_numpy(float), 0.90)) if len(resid) else 10.0
    default = float(h.median())
    p50 = pd.Series([float(p50_map.get(as_berlin(t).hour, default)) + bias for t in hours], index=hours)
    return pd.DataFrame({"p10": p50 + lo, "p50": p50, "p90": p50 + hi})


@dataclass
class SimConfig:
    speed: float = 0.0
    seed: int = 0
    costs: ExecutionCosts = field(default_factory=lambda: SOURCED_COSTS)
    battery: BatteryConfig | None = None
    risk: RiskLimits | None = None
    forecast_bias: float = 0.0  # used by forecast_failure
    on_tick: Callable[[dict[str, Any]], None] | None = None
    paper_trading_only: bool = True
    policy: str = "cost_aware"  # cost_aware | quantile_bids | cvar | id_reopt
    cvar_lambda: float = 2.0

    def __post_init__(self) -> None:
        if self.battery is None:
            self.battery = BatteryConfig(degradation_eur_per_mwh=0.0)  # wear lives in ExecutionCosts
        if self.risk is None:
            self.risk = RiskLimits(
                max_cycles_per_day=DEFAULT_CYCLES_PER_DAY,
                max_drawdown_eur=DEFAULT_DRAWDOWN_EUR,
                enable_kill_switch=True,
            )
        if self.policy not in POLICIES:
            raise ValueError(f"Unknown simulator policy {self.policy!r}. Known: {', '.join(POLICIES)}")


@dataclass
class Simulator:
    scenario: Scenario
    config: SimConfig = field(default_factory=SimConfig)

    def run(self) -> dict[str, Any]:
        cfg = self.config
        prices = self.scenario.prices.copy()
        prices.index = pd.DatetimeIndex([as_berlin(t) for t in prices.index])
        batt = cfg.battery or BatteryConfig()
        state = BatteryState.from_config(batt)
        # Threshold / ML / PF start from the same SoC independently
        state_ml = BatteryState.from_config(batt)
        state_th = BatteryState.from_config(batt)
        state_pf = BatteryState.from_config(batt)
        risk = RiskManager(cfg.risk or RiskLimits())
        clock = SimClock(prices.index, speed=cfg.speed)

        plan_ml: dict[pd.Timestamp, Decision] = {}
        plan_th: dict[pd.Timestamp, Decision] = {}
        plan_da: dict[pd.Timestamp, Decision] = {}
        bid_curves: dict[pd.Timestamp, object] = {}
        pending_delivery_hours: pd.DatetimeIndex | None = None
        rows: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        forecasts: dict[str, pd.DataFrame] = {}
        policy = cfg.policy

        # Oracle PF is computed once for the labelled baseline only; it is never
        # fed back into the agent's visible history or its schedule.
        pf_plan = _perfect_foresight(prices, batt, BatteryState.from_config(batt), cfg.costs)

        hist_ml = pd.Series(dtype=float)
        while not clock.done:
            ts = clock.step()
            if ts is None:
                break
            ts = as_berlin(ts)
            raw_px = prices.loc[ts] if ts in prices.index else np.nan
            visible = prices.loc[prices.index < ts]  # strictly before now: no lookahead
            # Threshold uses only visible history + current published? At a delivery
            # hour the DA price was published the previous afternoon; still, the
            # *schedule* for this day was locked at gate close. Threshold baseline
            # here also follows a day-locked plan from gate closure (fair compare).

            if is_gate_closure_tick(ts):
                delivery = (delivery_day(ts) + pd.Timedelta(days=1))
                hours = pd.date_range(delivery, periods=24, freq="h", tz="Europe/Berlin")
                hours = hours[hours.isin(prices.index)]
                bias = cfg.forecast_bias
                if self.scenario.name == "forecast_failure" and bias == 0.0:
                    bias = 80.0
                fan = _hour_climatology(visible, hours, bias=bias)
                forecasts[str(delivery.date())] = fan
                if len(hours):
                    start_ml = BatteryState(soc=state_ml.soc)
                    start_th = BatteryState(soc=state_th.soc)
                    plan_da = solve_day_lp_with_costs(
                        fan["p50"], batt, start_ml, cfg.costs, dt_h=1.0, note="sim_cost_aware"
                    )
                    plan_ml = dict(plan_da)
                    bid_curves = {}
                    pending_delivery_hours = hours
                    if policy == "quantile_bids":
                        bid_curves = build_curves_for_day(
                            fan["p10"], fan["p50"], fan["p90"], batt.power_mw, cfg.costs
                        )
                    elif policy == "cvar":
                        scen_paths = historical_day_scenarios(visible, hours, n_days=60)
                        if scen_paths:
                            plan_ml = solve_day_lp_cvar(
                                scen_paths, batt, start_ml, cfg.costs, lam=cfg.cvar_lambda, note="sim_cvar"
                            )
                    plan_th = _threshold_day(fan["p50"], batt, start_th)
                    events.append({
                        "ts": str(ts),
                        "type": "gate_closure",
                        "delivery_day": str(delivery.date()),
                        "policy": policy,
                        "visible_hours": int(len(visible)),
                        "forecast_p50_mean": float(fan["p50"].mean()) if len(fan) else None,
                    })

            if policy == "id_reopt" and is_da_publication_tick(ts) and pending_delivery_hours is not None:
                hours = pending_delivery_hours
                day_px = prices.reindex(hours).dropna()
                if len(day_px) and plan_da:
                    # Realised DA for tomorrow is public at this tick; not lookahead.
                    out = reoptimize_after_da(
                        plan_da, day_px, batt, state_ml.soc, IntradayLayerConfig(da_costs=cfg.costs)
                    )
                    phys = out["physical_actions"]
                    plan_ml = {}
                    for _, row in phys.iterrows():
                        plan_ml[pd.Timestamp(row["ts"])] = Decision(
                            charge_mw=float(row["charge_mw"]),
                            discharge_mw=float(row["discharge_mw"]),
                            note="sim_id_reopt",
                        )
                    events.append({
                        "ts": str(ts),
                        "type": "id_reopt",
                        "id_price_source": out["id_price_source"],
                        "id_throughput_mwh": out["id_throughput_mwh"],
                    })

            # Settlement at delivery ticks uses the realised (possibly NaN) price.
            def _act(plan, st, *, count_cycles=True):
                dec = plan.get(ts) or Decision()
                ch, dh = float(dec.charge_mw), float(dec.discharge_mw)
                if not np.isfinite(raw_px):
                    events.append({"ts": str(ts), "type": "data_outage", "action": "hold"})
                    ch, dh = 0.0, 0.0
                if risk.killed:
                    ch, dh = 0.0, 0.0
                ch, dh, _reasons = risk.clip_dispatch(
                    charge_mw=ch,
                    discharge_mw=dh,
                    power_mw=batt.power_mw,
                    soc=st.soc,
                    soc_min=batt.soc_min,
                    soc_max=batt.soc_max,
                    energy_mwh=batt.energy_mwh,
                    eta_charge=batt.eta_charge,
                    eta_discharge=batt.eta_discharge,
                    dt_h=1.0,
                    cycle_increment_if_full=0.0,
                )
                new_st, gin, gout = apply_dispatch(batt, st, charge_mw=ch, discharge_mw=dh, dt_h=1.0)
                if count_cycles:
                    risk.day_cycles += (gin + gout) / (2.0 * batt.energy_mwh) if batt.energy_mwh else 0.0
                return new_st, gin, gout, ch, dh

            risk.reset_day(str(delivery_day(ts).date()))
            if policy == "quantile_bids" and ts in bid_curves and np.isfinite(raw_px):
                ch_b, dh_b = bid_curves[ts].accepted_volume(float(raw_px))
                plan_ml[ts] = Decision(charge_mw=ch_b, discharge_mw=dh_b, note="sim_bid_clear")
            state_ml, gin_m, gout_m, ch_m, dh_m = _act(plan_ml, state_ml, count_cycles=True)
            state_th, gin_t, gout_t, ch_t, dh_t = _act(plan_th, state_th, count_cycles=False)
            if np.isfinite(raw_px):
                # Running net equity for the kill switch (fee+slip+deg on this tick).
                add = cfg.costs.fee_eur_per_mwh + cfg.costs.degradation_eur_per_mwh
                slip = cfg.costs.slippage_eur_per_mwh
                step = -gin_m * (float(raw_px) + slip) + gout_m * (float(raw_px) - slip) - (gin_m + gout_m) * add
                # stash on risk via a private running cash
                risk._cash = getattr(risk, "_cash", 0.0) + step
                risk.update_equity(float(risk._cash))
            dec_pf = pf_plan.get(ts) or Decision()
            if np.isfinite(raw_px) and not risk.killed:
                state_pf, gin_p, gout_p = apply_dispatch(
                    batt, state_pf, charge_mw=dec_pf.charge_mw, discharge_mw=dec_pf.discharge_mw, dt_h=1.0
                )
            else:
                gin_p = gout_p = 0.0

            px = float(raw_px) if np.isfinite(raw_px) else None
            row = {
                "ts": ts,
                "price": px if px is not None else np.nan,
                "visible_hours": int(len(visible)),
                "grid_in_mwh": gin_m,
                "grid_out_mwh": gout_m,
                "charge_mw": ch_m,
                "discharge_mw": dh_m,
                "soc": state_ml.soc,
                "cycles": state_ml.cycles,
                "th_grid_in_mwh": gin_t,
                "th_grid_out_mwh": gout_t,
                "th_soc": state_th.soc,
                "pf_grid_in_mwh": gin_p,
                "pf_grid_out_mwh": gout_p,
                "pf_soc": state_pf.soc,
                "killed": bool(risk.killed),
                "kill_reason": risk.kill_reason,
            }
            # Running equity after this tick (gross mid; net from costs later in batch)
            rows.append(row)
            if risk.killed and (not events or events[-1].get("type") != "kill_switch"):
                events.append({"ts": str(ts), "type": "kill_switch", "reason": risk.kill_reason})

            snap = {"ts": str(ts), "price": px, "soc": state_ml.soc, "killed": risk.killed}
            if cfg.on_tick:
                cfg.on_tick(snap)

        actions = pd.DataFrame(rows)
        if len(actions):
            actions = actions.reset_index(drop=True)

        def _pnl(gin_col, gout_col):
            acts = pd.DataFrame({
                "ts": actions["ts"],
                "price": actions["price"].fillna(0.0),
                "grid_in_mwh": actions[gin_col],
                "grid_out_mwh": actions[gout_col],
            })
            # Zero-price on outage hours with zero volume is fine (volume is 0).
            net = apply_costs_to_actions(acts, cfg.costs)
            gross = apply_costs_to_actions(acts, ExecutionCosts(0.0, 0.0, 0.0, label="zero"))
            return net, gross

        ml_net, ml_gross = _pnl("grid_in_mwh", "grid_out_mwh")
        th_net, th_gross = _pnl("th_grid_in_mwh", "th_grid_out_mwh")
        pf_net, pf_gross = _pnl("pf_grid_in_mwh", "pf_grid_out_mwh")

        # Update kill switch on net equity path
        if len(ml_net["equity_eur"]):
            for eq in ml_net["equity_eur"]:
                risk.update_equity(float(eq))
                if risk.killed:
                    break

        def _final(res):
            return float(res["final_cash_eur"])

        summary = {
            "paper_trading_only": True,
            "no_real_orders": True,
            "scenario": self.scenario.to_meta(),
            "seed": cfg.seed,
            "speed": cfg.speed,
            "gate_closure": "12:00 Europe/Berlin on D-1; no lookahead into delivery-day prices",
            "policy": policy,
            "cvar_lambda": cfg.cvar_lambda if policy == "cvar" else None,
            "costs": cfg.costs.to_dict(),
            "battery": asdict(batt),
            "risk": {
                "max_cycles_per_day": cfg.risk.max_cycles_per_day if cfg.risk else None,
                "max_drawdown_eur": cfg.risk.max_drawdown_eur if cfg.risk else None,
                "killed": bool(risk.killed),
                "kill_reason": risk.kill_reason,
            },
            "pnl": {
                "ml_gross_eur": _final(ml_gross),
                "ml_net_eur": _final(ml_net),
                "threshold_gross_eur": _final(th_gross),
                "threshold_net_eur": _final(th_net),
                "perfect_foresight_gross_eur": _final(pf_gross),
                "perfect_foresight_net_eur": _final(pf_net),
            },
            "capture_vs_pf_net_pct": (
                100.0 * _final(ml_net) / _final(pf_net) if _final(pf_net) else None
            ),
            "events": events,
            "forecasts": {k: v.to_dict(orient="list") | {"index": [str(i) for i in v.index]} for k, v in forecasts.items()},
            "n_ticks": int(len(actions)),
            "limitations": [
                "Paper trading only — no exchange connectivity, no real orders.",
                "Intraday/imbalance uses labelled proxies (ID mid = DA, reBAP = DA) when policy=id_reopt; Energy-Charts has no public ID series and official reBAP needs OAuth. Tick accounting still applies the DA fee preset.",
                "Sourced fee preset is ECC DA clearing only; current EPEX trading fee is not in the public price list; degradation is still ASSUMED.",
                "Perfect foresight is an oracle baseline with lookahead; the agent never sees it.",
                "These figures are not real-money performance.",
            ],
        }
        summary["actions"] = actions
        summary["equity"] = {
            "ml_net": ml_net["equity_eur"],
            "ml_gross": ml_gross["equity_eur"],
            "threshold_net": th_net["equity_eur"],
            "perfect_foresight_net": pf_net["equity_eur"],
        }
        return summary


def _threshold_day(prices: pd.Series, battery: BatteryConfig, state: BatteryState) -> dict[pd.Timestamp, Decision]:
    strat = ThresholdArbitrage()
    hist = pd.Series(dtype=float)
    out: dict[pd.Timestamp, Decision] = {}
    st = BatteryState(soc=state.soc)
    for ts, px in prices.items():
        hist = pd.concat([hist, pd.Series({ts: float(px)})])
        out[pd.Timestamp(ts)] = strat.decide(
            ts=pd.Timestamp(ts), price=float(px), history=hist, battery=battery, state=st, remaining_day_prices=None
        )
        # do not advance SoC here; settlement advances it later
    return out


def _perfect_foresight(
    prices: pd.Series, battery: BatteryConfig, state: BatteryState, costs: ExecutionCosts
) -> dict[pd.Timestamp, Decision]:
    """Oracle: day-by-day LP on realised prices. Labelled baseline only."""
    plan: dict[pd.Timestamp, Decision] = {}
    px = prices.dropna().copy()
    if px.empty:
        return plan
    st = BatteryState(soc=state.soc)
    px.index = pd.DatetimeIndex([as_berlin(t) for t in px.index])
    for _, day_px in px.groupby(px.index.date):
        part = solve_day_lp_with_costs(day_px, battery, st, costs, dt_h=1.0, note="oracle_pf")
        plan.update(part)
        # Advance oracle SoC on realised dispatch so the next day starts consistently
        for ts, dec in part.items():
            st, _, _ = apply_dispatch(battery, st, charge_mw=dec.charge_mw, discharge_mw=dec.discharge_mw, dt_h=1.0)
    return plan


def run_simulation(scenario: Scenario, config: SimConfig | None = None) -> dict[str, Any]:
    return Simulator(scenario, config or SimConfig()).run()
