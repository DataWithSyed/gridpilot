"""SDAC-style day-ahead gate-closure bid curves (paper trading only).

At 12:00 Europe/Berlin on D-1, turn P10/P50/P90 forecast fans into
price-quantity curves. Curves are cleared against the realised day-ahead
clearing price with partial acceptance at the marginal price step and
when SoC or power caps the fill. This module never places real orders.

The locked-schedule baseline is the current cost-aware LP on the same
P50 path: volume is committed regardless of the realised price (a
price-taking fill). Bid curves let volume respond to the clearing price.

Tie-break when a limit equals the clearing price: accept
``MARGINAL_ACCEPT_FRACTION`` (0.5) of that step. This is an ASSUMED
stand-in for SDAC residual volume matching; we do not have the market
merit-order curve.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gridpilot_backtest.costs import ExecutionCosts, apply_costs_to_actions
from gridpilot_core.battery import BatteryConfig, BatteryState, apply_dispatch
from gridpilot_core.strategy import Decision
from gridpilot_forecast.cost_aware_lp import cycle_addend_eur_per_mwh, solve_day_lp_with_costs

GATE_CLOSURE_HOUR = 12
GATE_CLOSURE_TZ = "Europe/Berlin"
MARGINAL_ACCEPT_FRACTION = 0.5  # ASSUMED tie-break at limit == clearing price
DEFAULT_N_STEPS = 3
_EPS = 1e-12


def gate_closure_time(delivery: pd.Timestamp | str) -> pd.Timestamp:
    """Return 12:00 Europe/Berlin on D-1 for a delivery-day timestamp or date."""
    d = pd.Timestamp(delivery)
    if d.tzinfo is None:
        d = d.tz_localize(GATE_CLOSURE_TZ)
    else:
        d = d.tz_convert(GATE_CLOSURE_TZ)
    midnight = pd.Timestamp(d.date(), tz=GATE_CLOSURE_TZ)
    return (midnight - pd.Timedelta(days=1)).replace(
        hour=GATE_CLOSURE_HOUR, minute=0, second=0, microsecond=0
    )


@dataclass(frozen=True)
class BidStep:
    """One incremental price-quantity step on an hourly curve."""

    limit_eur_mwh: float
    quantity_mw: float


@dataclass(frozen=True)
class HourBidCurve:
    """Buy (charge) and sell (discharge) steps for one delivery hour."""

    ts: pd.Timestamp
    buy_steps: tuple[BidStep, ...]  # descending limits: most aggressive first
    sell_steps: tuple[BidStep, ...]  # ascending limits: most aggressive first
    note: str = ""

    def accepted_volume(
        self,
        clearing_price: float,
        *,
        marginal_frac: float = MARGINAL_ACCEPT_FRACTION,
    ) -> tuple[float, float]:
        """Return (charge_mw, discharge_mw) after price clearing, before SoC."""
        px = float(clearing_price)
        charge = _accepted_mw(self.buy_steps, px, is_buy=True, frac=marginal_frac)
        discharge = _accepted_mw(self.sell_steps, px, is_buy=False, frac=marginal_frac)
        if charge > _EPS and discharge > _EPS:
            if charge >= discharge:
                charge -= discharge
                discharge = 0.0
            else:
                discharge -= charge
                charge = 0.0
        return charge, discharge


def _merge_steps(steps: list[BidStep], *, descending: bool) -> tuple[BidStep, ...]:
    kept = [s for s in steps if s.quantity_mw > _EPS]
    if not kept:
        return ()
    kept.sort(key=lambda s: s.limit_eur_mwh, reverse=descending)
    merged = [kept[0]]
    for s in kept[1:]:
        last = merged[-1]
        if abs(s.limit_eur_mwh - last.limit_eur_mwh) <= 1e-9:
            merged[-1] = BidStep(last.limit_eur_mwh, last.quantity_mw + s.quantity_mw)
        else:
            merged.append(s)
    return tuple(merged)


def _accepted_mw(
    steps: tuple[BidStep, ...],
    price: float,
    *,
    is_buy: bool,
    frac: float,
) -> float:
    acc = 0.0
    for s in steps:
        if is_buy:
            if s.limit_eur_mwh > price + _EPS:
                acc += s.quantity_mw
            elif abs(s.limit_eur_mwh - price) <= _EPS:
                acc += s.quantity_mw * frac
        else:
            if s.limit_eur_mwh < price - _EPS:
                acc += s.quantity_mw
            elif abs(s.limit_eur_mwh - price) <= _EPS:
                acc += s.quantity_mw * frac
    return float(acc)


def build_quantile_bid_curve(
    *,
    ts: pd.Timestamp,
    p10: float,
    p50: float,
    p90: float,
    power_mw: float,
    costs: ExecutionCosts,
    n_steps: int = DEFAULT_N_STEPS,
    note: str = "quantile_bid",
) -> HourBidCurve:
    """Build a 3-step (default) buy/sell curve around P10/P50/P90 and costs.

    Buy limits run from ``p50 - add`` (aggressive) down to ``p10 - add``.
    Sell limits run from ``p50 + add`` up to ``p90 + add``.
    ``add`` is the sourced/assumed cycle addend (fee + slippage + degradation).
    Curves are uncrossed so the highest buy limit stays strictly below the
    lowest sell limit.
    """
    lo, mid, hi = float(p10), float(p50), float(p90)
    if lo > mid:
        lo = mid
    if hi < mid:
        hi = mid
    add = cycle_addend_eur_per_mwh(costs)
    n_steps = max(int(n_steps), 1)
    qty = float(power_mw) / n_steps
    gap = add if add > 0 else 0.01
    if n_steps == 1:
        buy_limits = [mid - add]
        sell_limits = [mid + add]
    else:
        buy_limits = list(np.linspace(mid - add, lo - add, n_steps))
        sell_limits = list(np.linspace(mid + add, hi + add, n_steps))
    buy_limits = [min(float(L), mid - gap) for L in buy_limits]
    sell_limits = [max(float(L), mid + gap) for L in sell_limits]
    buy = _merge_steps([BidStep(L, qty) for L in buy_limits], descending=True)
    sell = _merge_steps([BidStep(L, qty) for L in sell_limits], descending=False)
    return HourBidCurve(ts=ts, buy_steps=buy, sell_steps=sell, note=note)


def build_curves_for_day(
    p10: pd.Series,
    p50: pd.Series,
    p90: pd.Series,
    power_mw: float,
    costs: ExecutionCosts,
    *,
    n_steps: int = DEFAULT_N_STEPS,
    note: str = "quantile_bid",
) -> dict[pd.Timestamp, HourBidCurve]:
    """Build one hourly curve per timestamp on the shared forecast index."""
    idx = p50.index
    curves: dict[pd.Timestamp, HourBidCurve] = {}
    for ts in idx:
        curves[ts] = build_quantile_bid_curve(
            ts=ts,
            p10=float(p10.loc[ts]),
            p50=float(p50.loc[ts]),
            p90=float(p90.loc[ts]),
            power_mw=power_mw,
            costs=costs,
            n_steps=n_steps,
            note=note,
        )
    return curves


def build_schedule_anchored_curves(
    p10: pd.Series,
    p50: pd.Series,
    p90: pd.Series,
    plan: dict[pd.Timestamp, Decision],
    power_mw: float,
    costs: ExecutionCosts,
) -> dict[pd.Timestamp, HourBidCurve]:
    """Centre volume on the locked P50 schedule; add P10/P90 tail steps.

    Planned charge (discharge) is bid at ``p50 - add`` (``p50 + add``).
    Unused capacity is offered only in the cheap / expensive tail so a
    hold hour can still react to extremes. Paper only.
    """
    add = cycle_addend_eur_per_mwh(costs)
    gap = add if add > 0 else 0.01
    curves: dict[pd.Timestamp, HourBidCurve] = {}
    for ts in p50.index:
        lo = min(float(p10.loc[ts]), float(p50.loc[ts]))
        mid = float(p50.loc[ts])
        hi = max(float(p90.loc[ts]), mid)
        d = plan.get(ts, Decision())
        q_ch = max(0.0, float(d.charge_mw))
        q_dis = max(0.0, float(d.discharge_mw))
        buy: list[BidStep] = []
        sell: list[BidStep] = []
        if q_ch > _EPS:
            buy.append(BidStep(min(mid - add, mid - gap), min(q_ch, power_mw)))
            slack = max(0.0, power_mw - q_ch)
            if slack > _EPS:
                buy.append(BidStep(min(lo - add, mid - gap), slack))
        elif q_dis > _EPS:
            sell.append(BidStep(max(mid + add, mid + gap), min(q_dis, power_mw)))
            slack = max(0.0, power_mw - q_dis)
            if slack > _EPS:
                sell.append(BidStep(max(hi + add, mid + gap), slack))
        else:
            buy.append(BidStep(min(lo - add, mid - gap), power_mw / 3.0))
            sell.append(BidStep(max(hi + add, mid + gap), power_mw / 3.0))
        curves[ts] = HourBidCurve(
            ts=ts,
            buy_steps=_merge_steps(buy, descending=True),
            sell_steps=_merge_steps(sell, descending=False),
            note="anchored_bid",
        )
    return curves


def rolling_hod_quantiles(
    history: pd.Series,
    index: pd.DatetimeIndex,
    *,
    lookback_days: int = 90,
    quantiles: tuple[float, ...] = (0.10, 0.50, 0.90),
) -> dict[float, pd.Series]:
    """Causal hour-of-day climatology on ``history`` strictly before ``index[0]``."""
    if len(index) == 0:
        return {q: pd.Series(dtype=float) for q in quantiles}
    cutoff = index[0]
    h = history[history.index < cutoff].astype(float)
    if lookback_days is not None and lookback_days > 0 and len(h):
        start = cutoff - pd.Timedelta(days=int(lookback_days))
        h = h[h.index >= start]
    out: dict[float, pd.Series] = {}
    if len(h) == 0:
        zeros = pd.Series(0.0, index=index)
        return {q: zeros.copy() for q in quantiles}
    hours = h.index.tz_convert(GATE_CLOSURE_TZ).hour if h.index.tz is not None else h.index.hour
    for q in quantiles:
        by = h.groupby(hours).quantile(float(q))
        fallback = float(h.quantile(float(q)))
        vals = []
        for ts in index:
            hr = ts.tz_convert(GATE_CLOSURE_TZ).hour if getattr(ts, "tzinfo", None) else pd.Timestamp(ts).hour
            vals.append(float(by[hr]) if hr in by.index else fallback)
        out[float(q)] = pd.Series(vals, index=index, dtype=float)
    return out


def _new_state(soc: float) -> BatteryState:
    return BatteryState(soc=float(soc))


def _walk_day(
    prices: pd.Series,
    charge_mw: pd.Series,
    discharge_mw: pd.Series,
    battery: BatteryConfig,
    soc: float,
    *,
    dt_h: float,
    note: str,
) -> pd.DataFrame:
    st = _new_state(soc)
    rows = []
    for ts, px in prices.items():
        ch = float(charge_mw.get(ts, 0.0)) if hasattr(charge_mw, "get") else float(charge_mw.loc[ts])
        dis = float(discharge_mw.get(ts, 0.0)) if hasattr(discharge_mw, "get") else float(discharge_mw.loc[ts])
        ch = max(0.0, ch)
        dis = max(0.0, dis)
        if ch > _EPS and dis > _EPS:
            if ch >= dis:
                ch, dis = ch - dis, 0.0
            else:
                dis, ch = dis - ch, 0.0
        new_st, gin, gout = apply_dispatch(
            battery, st, charge_mw=ch, discharge_mw=dis, dt_h=dt_h
        )
        filled_note = note
        if gin + _EPS < ch * dt_h or gout + _EPS < dis * dt_h:
            filled_note = f"{note}|soc_partial"
        rows.append(
            {
                "ts": ts,
                "price": float(px),
                "charge_mw": gin / dt_h if dt_h else 0.0,
                "discharge_mw": gout / dt_h if dt_h else 0.0,
                "grid_in_mwh": float(gin),
                "grid_out_mwh": float(gout),
                "cash": 0.0,
                "soc": float(new_st.soc),
                "note": filled_note,
            }
        )
        st = new_st
    return pd.DataFrame(rows)


def settle_locked_schedule(
    plan: dict[pd.Timestamp, Decision],
    prices: pd.Series,
    battery: BatteryConfig,
    soc: float,
    *,
    dt_h: float = 1.0,
    note: str = "locked_schedule",
) -> pd.DataFrame:
    """Walk a price-taking locked MW schedule, clipping to SoC and power."""
    ch = pd.Series({ts: d.charge_mw for ts, d in plan.items()}, dtype=float)
    dis = pd.Series({ts: d.discharge_mw for ts, d in plan.items()}, dtype=float)
    return _walk_day(prices, ch, dis, battery, soc, dt_h=dt_h, note=note)


def clear_day_curves(
    curves: dict[pd.Timestamp, HourBidCurve],
    prices: pd.Series,
    battery: BatteryConfig,
    soc: float,
    *,
    dt_h: float = 1.0,
) -> pd.DataFrame:
    """Clear hourly curves against realised prices, then clip to SoC."""
    ch_map = {}
    dis_map = {}
    notes = {}
    for ts, px in prices.items():
        curve = curves.get(ts)
        if curve is None:
            ch_map[ts] = 0.0
            dis_map[ts] = 0.0
            notes[ts] = "no_curve"
        else:
            ch_map[ts], dis_map[ts] = curve.accepted_volume(float(px))
            notes[ts] = curve.note or "bid_clear"
    df = _walk_day(
        prices,
        pd.Series(ch_map, dtype=float),
        pd.Series(dis_map, dtype=float),
        battery,
        soc,
        dt_h=dt_h,
        note="bid_clear",
    )
    if len(df):
        df["note"] = [
            notes.get(ts, n) if "soc_partial" not in str(n) else f"{notes.get(ts, 'bid_clear')}|soc_partial"
            for ts, n in zip(df["ts"], df["note"])
        ]
    return df


def policy_summary(actions: pd.DataFrame, costs: ExecutionCosts, initial_cash: float = 0.0) -> dict:
    """Final cash, daily PnL and ending SoC for a paper action frame."""
    out = apply_costs_to_actions(actions, costs, initial_cash_eur=initial_cash)
    end_soc = float(actions["soc"].iloc[-1]) if len(actions) and "soc" in actions.columns else float("nan")
    cycles = float("nan")
    if len(actions):
        thr = float(actions["grid_in_mwh"].sum() + actions["grid_out_mwh"].sum())
        # cycles need energy capacity; leave to the caller when known
        out["throughput_mwh_day"] = thr
    out["end_soc"] = end_soc
    out["cycles"] = cycles
    return out


def evaluate_day(
    prices: pd.Series,
    p10: pd.Series,
    p50: pd.Series,
    p90: pd.Series,
    battery: BatteryConfig,
    costs: ExecutionCosts,
    *,
    soc_schedule: float,
    soc_quantile: float,
    soc_anchored: float,
    dt_h: float = 1.0,
    n_steps: int = DEFAULT_N_STEPS,
) -> dict[str, pd.DataFrame]:
    """Lock a P50 cost-aware schedule and clear quantile / anchored bids.

    All three policies see the same forecast fan. SoC is tracked separately
    so the comparison stays fair. Paper trading only.
    """
    st_sched = _new_state(soc_schedule)
    plan = solve_day_lp_with_costs(p50, battery, st_sched, costs, dt_h=dt_h, note="locked_schedule")
    sched = settle_locked_schedule(plan, prices, battery, soc_schedule, dt_h=dt_h)
    q_curves = build_curves_for_day(p10, p50, p90, battery.power_mw, costs, n_steps=n_steps)
    q_acts = clear_day_curves(q_curves, prices, battery, soc_quantile, dt_h=dt_h)
    a_curves = build_schedule_anchored_curves(p10, p50, p90, plan, battery.power_mw, costs)
    a_acts = clear_day_curves(a_curves, prices, battery, soc_anchored, dt_h=dt_h)
    return {"schedule": sched, "quantile_bid": q_acts, "anchored_bid": a_acts, "plan": plan}
