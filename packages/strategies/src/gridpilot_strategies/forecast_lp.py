"""Forecast-driven daily LP strategies (paper trading only)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_core.strategy import Decision
from gridpilot_strategies.quantile_forecast import RollingQuantilePriceForecast


def _solve_day_lp(
    prices: pd.Series,
    battery: BatteryConfig,
    state: BatteryState,
    *,
    dt_h: float = 1.0,
) -> dict[pd.Timestamp, Decision]:
    prices = prices.astype(float)
    T = len(prices)
    if T == 0:
        return {}
    n = 2 * T
    c_price = prices.to_numpy()
    deg = battery.degradation_eur_per_mwh
    c_obj = np.concatenate([c_price + deg, -c_price + deg])
    e0 = state.soc * battery.energy_mwh
    e_min = battery.soc_min * battery.energy_mwh
    e_max = battery.soc_max * battery.energy_mwh
    emax = battery.power_mw * dt_h
    bounds = [(0.0, emax)] * T + [(0.0, emax)] * T
    A_ub = []
    b_ub = []
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
    res = linprog(c_obj, A_ub=np.asarray(A_ub), b_ub=np.asarray(b_ub), bounds=bounds, method="highs")
    plan: dict[pd.Timestamp, Decision] = {}
    if not res.success:
        for ts in prices.index:
            plan[ts] = Decision(note=f"lp_fail:{res.message}")
        return plan
    x = res.x
    scale = 1.0 / dt_h if dt_h > 0 else 0.0
    for i, ts in enumerate(prices.index):
        plan[ts] = Decision(
            charge_mw=float(x[i]) * scale,
            discharge_mw=float(x[T + i]) * scale,
            note="forecast_lp",
        )
    return plan


@dataclass
class ForecastDrivenLP:
    """Re-optimise each hour on a rolling P50 price forecast for the rest of the day.

    Causal: forecast uses only past prices; realised fill uses the true current
    price in the paper agent (as with all strategies).
    """

    name: str = "forecast_driven_lp"
    dt_h: float = 1.0
    forecast: RollingQuantilePriceForecast = field(default_factory=RollingQuantilePriceForecast)
    price_quantile: float = 0.50
    reoptimize_each_hour: bool = True
    _plan: dict[pd.Timestamp, Decision] | None = None
    _plan_day: str | None = None

    def decide(
        self,
        *,
        ts: pd.Timestamp,
        price: float,
        history: pd.Series,
        battery: BatteryConfig,
        state: BatteryState,
        remaining_day_prices: pd.Series | None = None,
    ) -> Decision:
        _ = price
        if remaining_day_prices is None or remaining_day_prices.empty:
            return Decision(note="no_day_prices")
        day_key = str(ts.tz_convert("Europe/Berlin").date()) if ts.tzinfo else str(pd.Timestamp(ts).date())
        need = self.reoptimize_each_hour or self._plan is None or self._plan_day != day_key
        if need:
            fc = self.forecast.forecast_day(history, remaining_day_prices.index)
            q = self.price_quantile
            # Use nearest available quantile key
            if q not in fc:
                q = min(fc.keys(), key=lambda k: abs(k - self.price_quantile))
            # Pin the current hour to the known realised price in the forecast path
            path = fc[q].copy()
            path.iloc[0] = float(history.iloc[-1]) if len(history) else float(price)
            self._plan = _solve_day_lp(path, battery, state, dt_h=self.dt_h)
            self._plan_day = day_key
        return self._plan.get(ts, Decision(note="unplanned_hour"))


@dataclass
class RiskAwareForecastLP:
    """LP on a pessimistic price path: P10 for discharge value, P90 for charge cost.

    Implementation: build a synthetic path that uses P90 where the P50 path would
    charge (high cost) and P10 where it would discharge (low revenue) after a
    first-pass P50 plan — one-shot robustification. Simpler fallback: optimise
    directly on the P10 path (conservative revenue).

    Mode ``pessimistic_path`` (default): objective prices = 0.5*P10 + 0.5*P50 for
    a mild conservative tilt (ASSUMED blend). Mode ``p10_only``: pure P10 path.
    """

    name: str = "risk_aware_forecast_lp"
    dt_h: float = 1.0
    forecast: RollingQuantilePriceForecast = field(default_factory=RollingQuantilePriceForecast)
    mode: str = "pessimistic_path"  # or "p10_only"
    reoptimize_each_hour: bool = True
    _plan: dict[pd.Timestamp, Decision] | None = None
    _plan_day: str | None = None

    def decide(
        self,
        *,
        ts: pd.Timestamp,
        price: float,
        history: pd.Series,
        battery: BatteryConfig,
        state: BatteryState,
        remaining_day_prices: pd.Series | None = None,
    ) -> Decision:
        _ = price
        if remaining_day_prices is None or remaining_day_prices.empty:
            return Decision(note="no_day_prices")
        day_key = str(ts.tz_convert("Europe/Berlin").date()) if ts.tzinfo else str(pd.Timestamp(ts).date())
        need = self.reoptimize_each_hour or self._plan is None or self._plan_day != day_key
        if need:
            fc = self.forecast.forecast_day(history, remaining_day_prices.index)
            p10 = fc.get(0.10)
            p50 = fc.get(0.50)
            p90 = fc.get(0.90)
            if p10 is None or p50 is None:
                path = next(iter(fc.values())).copy()
            elif self.mode == "p10_only":
                path = p10.copy()
            else:
                # ASSUMED: blend P10 and P50; optionally pull toward P90 on high hours
                path = (0.5 * p10 + 0.5 * p50).copy()
                if p90 is not None:
                    # hours where P90-P10 spread is large: tilt slightly more pessimistic
                    spread = (p90 - p10).clip(lower=0)
                    tilt = (spread / (spread.median() + 1e-9)).clip(0, 1) * 0.15
                    path = (1 - tilt) * path + tilt * p10
            path.iloc[0] = float(history.iloc[-1]) if len(history) else float(price)
            self._plan = _solve_day_lp(path, battery, state, dt_h=self.dt_h)
            for ts_k, dec in self._plan.items():
                self._plan[ts_k] = Decision(
                    charge_mw=dec.charge_mw,
                    discharge_mw=dec.discharge_mw,
                    note="risk_aware_lp",
                )
            self._plan_day = day_key
        return self._plan.get(ts, Decision(note="unplanned_hour"))
