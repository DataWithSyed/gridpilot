"""Cost-aware CVaR dispatch LP and a return-vs-CVaR frontier (paper only).

A here-and-now daily schedule is chosen against a set of causal price
scenarios. The Rockafellar–Uryasev formulation trades off expected cash
against CVaR of loss at level ``alpha`` (default 5%), with sourced (or
other) ``ExecutionCosts`` in every scenario cash path.

    maximize  E[cash] - lambda * CVaR_alpha(loss)

Scenarios default to the last ``n_scenarios`` completed Berlin days of
realised prices, mapped onto today's hours (causal climatology paths).
This is not a stochastic-volatility model. Paper trading only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from gridpilot_backtest.costs import ExecutionCosts, SOURCED_COSTS
from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_core.strategy import Decision
from gridpilot_forecast.cost_aware_lp import cycle_addend_eur_per_mwh, solve_day_lp_with_costs

DEFAULT_LAMBDA_GRID = (0.0, 0.5, 1.0, 2.0, 5.0, 10.0)
DEFAULT_ALPHA = 0.05
DEFAULT_N_SCENARIOS = 60
GATE_TZ = "Europe/Berlin"


def historical_day_scenarios(
    history: pd.Series,
    index: pd.DatetimeIndex,
    *,
    n_days: int = DEFAULT_N_SCENARIOS,
) -> list[pd.Series]:
    """Causal same-hour paths from the last ``n_days`` completed days before ``index[0]``."""
    if len(index) == 0 or len(history) == 0:
        return []
    cutoff = index[0]
    h = history[history.index < cutoff].astype(float)
    if len(h) == 0:
        return []
    dates = pd.Index(h.index.tz_convert(GATE_TZ).date if h.index.tz is not None else h.index.date).unique()
    dates = dates[-int(n_days):]
    out: list[pd.Series] = []
    hours_today = [ts.tz_convert(GATE_TZ).hour if getattr(ts, "tzinfo", None) else pd.Timestamp(ts).hour for ts in index]
    for d in dates:
        mask = (h.index.tz_convert(GATE_TZ).date if h.index.tz is not None else h.index.date) == d
        day = h.loc[mask]
        if day.empty:
            continue
        by_hour = {}
        for ts, val in day.items():
            hr = ts.tz_convert(GATE_TZ).hour if getattr(ts, "tzinfo", None) else pd.Timestamp(ts).hour
            by_hour[hr] = float(val)
        fallback = float(day.mean())
        out.append(pd.Series([by_hour.get(hr, fallback) for hr in hours_today], index=index, dtype=float))
    return out


def _loss_coeffs(prices: np.ndarray, costs: ExecutionCosts) -> tuple[np.ndarray, np.ndarray]:
    """Linear loss coefficients for (g_in, g_out) at these prices (slip=buy/sell)."""
    add = cycle_addend_eur_per_mwh(costs)
    # loss = sum gin*(price+slip+fee+deg) + gout*(-price+slip+fee+deg)
    # cycle_addend already is fee+slip+deg; buy worsens by slip already in add if slip in add.
    # Settlement: cash = -gin*(price+slip) + gout*(price-slip) - thr*(fee+deg)
    # loss = gin*(price+slip+fee+deg) + gout*(-price+slip+fee+deg)
    slip = costs.slippage_eur_per_mwh
    fee_deg = costs.fee_eur_per_mwh + costs.degradation_eur_per_mwh
    c_in = prices + slip + fee_deg
    c_out = -prices + slip + fee_deg
    return c_in, c_out


def solve_day_lp_cvar(
    scenarios: list[pd.Series],
    battery: BatteryConfig,
    state: BatteryState,
    costs: ExecutionCosts,
    *,
    lam: float = 1.0,
    alpha: float = DEFAULT_ALPHA,
    dt_h: float = 1.0,
    probs: np.ndarray | None = None,
    note: str = "cvar_lp",
) -> dict[pd.Timestamp, Decision]:
    """Here-and-now cost-aware CVaR LP on price scenarios. Paper only."""
    if not scenarios:
        return {}
    idx = scenarios[0].index
    T = len(idx)
    S = len(scenarios)
    if T == 0:
        return {}
    P = np.vstack([s.astype(float).reindex(idx).to_numpy() for s in scenarios])
    if np.isnan(P).any():
        col_mean = np.nanmean(P, axis=0)
        inds = np.where(np.isnan(P))
        P[inds] = np.take(col_mean, inds[1])
        P = np.nan_to_num(P, nan=0.0)
    if probs is None:
        p = np.full(S, 1.0 / S)
    else:
        p = np.asarray(probs, float)
        p = p / p.sum()
    alpha = min(max(float(alpha), 1e-6), 0.999)  # tail probability (worst α)
    lam = float(lam)

    # variables: gin[0:T], gout[T:2T], zeta[2T], u[2T+1:]
    n = 2 * T + 1 + S
    c = np.zeros(n)
    for s in range(S):
        c_in, c_out = _loss_coeffs(P[s], costs)
        c[0:T] += p[s] * c_in
        c[T:2 * T] += p[s] * c_out
    c[2 * T] = lam
    c[2 * T + 1:] = lam * p / alpha

    emax = battery.power_mw * dt_h
    bounds = [(0.0, emax)] * T + [(0.0, emax)] * T + [(None, None)] + [(0.0, None)] * S

    A_ub = []
    b_ub = []
    e0 = state.soc * battery.energy_mwh
    e_min = battery.soc_min * battery.energy_mwh
    e_max = battery.soc_max * battery.energy_mwh
    eta_c = battery.eta_charge
    eta_d = battery.eta_discharge
    for t in range(T):
        row_hi = np.zeros(n)
        row_lo = np.zeros(n)
        for k in range(t + 1):
            row_hi[k] = eta_c
            row_hi[T + k] = -1.0 / eta_d
            row_lo[k] = -eta_c
            row_lo[T + k] = 1.0 / eta_d
        A_ub.append(row_hi)
        b_ub.append(e_max - e0)
        A_ub.append(row_lo)
        b_ub.append(-(e_min - e0))

    # u_s + zeta >= loss_s  =>  loss_coeff·g - u_s - zeta <= 0
    for s in range(S):
        row = np.zeros(n)
        c_in, c_out = _loss_coeffs(P[s], costs)
        row[0:T] = c_in
        row[T:2 * T] = c_out
        row[2 * T] = -1.0
        row[2 * T + 1 + s] = -1.0
        A_ub.append(row)
        b_ub.append(0.0)

    res = linprog(c, A_ub=np.asarray(A_ub), b_ub=np.asarray(b_ub), bounds=bounds, method="highs")
    plan: dict[pd.Timestamp, Decision] = {}
    if not res.success:
        mean_path = pd.Series(P.mean(axis=0), index=idx)
        return solve_day_lp_with_costs(mean_path, battery, state, costs, dt_h=dt_h, note=f"cvar_lp_fail:{res.message}")
    x = res.x
    for i, ts in enumerate(idx):
        gin = float(max(0.0, x[i]))
        gout = float(max(0.0, x[T + i]))
        plan[ts] = Decision(charge_mw=gin / dt_h if dt_h else 0.0, discharge_mw=gout / dt_h if dt_h else 0.0, note=note)
    return plan


def in_sample_expected_cash(
    plan: dict[pd.Timestamp, Decision],
    scenarios: list[pd.Series],
    costs: ExecutionCosts,
    *,
    dt_h: float = 1.0,
    probs: np.ndarray | None = None,
) -> float:
    """Expected energy+fee cash of a locked plan under the scenario measure (no SoC re-walk)."""
    if not scenarios or not plan:
        return float("nan")
    S = len(scenarios)
    p = np.full(S, 1.0 / S) if probs is None else np.asarray(probs, float)
    p = p / p.sum()
    total = 0.0
    for w, sc in zip(p, scenarios):
        cash = 0.0
        for ts, px in sc.items():
            d = plan.get(ts, Decision())
            gin = d.charge_mw * dt_h
            gout = d.discharge_mw * dt_h
            buy = float(px) + costs.slippage_eur_per_mwh
            sell = float(px) - costs.slippage_eur_per_mwh
            thr = gin + gout
            cash += -gin * buy + gout * sell - thr * (costs.fee_eur_per_mwh + costs.degradation_eur_per_mwh)
        total += float(w) * cash
    return float(total)
