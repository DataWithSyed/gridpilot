"""Cost-aware paper dispatch LP (fees, slippage, degradation in the objective).

Paper trading only — never places real orders. Strategies re-optimise under
``ExecutionCosts`` rather than applying costs only after fills.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from gridpilot_backtest.costs import ExecutionCosts
from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_core.strategy import Decision

try:
    from gridpilot_forecast.forecaster import WalkForwardQuantileForecast
except Exception:  # pragma: no cover
    WalkForwardQuantileForecast = None  # type: ignore


def cycle_addend_eur_per_mwh(costs: ExecutionCosts) -> float:
    """Per-MWh addend on both charge and discharge sides of the LP objective."""
    return float(
        costs.fee_eur_per_mwh + costs.slippage_eur_per_mwh + costs.degradation_eur_per_mwh
    )


def solve_day_lp_with_costs(
    prices: pd.Series,
    battery: BatteryConfig,
    state: BatteryState,
    costs: ExecutionCosts,
    *,
    dt_h: float = 1.0,
    note: str = "cost_aware_lp",
) -> dict[pd.Timestamp, Decision]:
    """Daily LP with buy/sell worsened by fee + slippage + degradation.

    Objective (minimise):
    sum_t  grid_in_t  * (price_t + add) + grid_out_t * (-price_t + add)
    where add = fee + slippage + degradation (€/MWh). BatteryConfig.degradation
    is *not* added again — pass costs.degradation_eur_per_mwh instead.
    """
    prices = prices.astype(float)
    T = len(prices)
    if T == 0:
        return {}
    n = 2 * T
    c_price = prices.to_numpy()
    add = cycle_addend_eur_per_mwh(costs)
    c_obj = np.concatenate([c_price + add, -c_price + add])
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
            note=note,
        )
    return plan


@dataclass
class CostAwareForecastDrivenLP:
    """Forecast-driven LP that re-optimises under ExecutionCosts (paper only)."""

    name: str = "cost_aware_forecast_driven_lp"
    dt_h: float = 1.0
    forecast: object | None = None
    price_quantile: float = 0.50
    costs: ExecutionCosts = field(default_factory=ExecutionCosts)
    reoptimize_each_hour: bool = True
    _plan: dict[pd.Timestamp, Decision] | None = field(default=None, repr=False)
    _plan_day: str | None = field(default=None, repr=False)

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
        if self.forecast is None:
            raise ImportError("forecast object is required for CostAwareForecastDrivenLP")
        day_key = str(ts.tz_convert("Europe/Berlin").date()) if ts.tzinfo else str(pd.Timestamp(ts).date())
        need = self.reoptimize_each_hour or self._plan is None or self._plan_day != day_key
        if need:
            fc = self.forecast.forecast_day(history, remaining_day_prices.index)
            q = self.price_quantile
            if q not in fc:
                q = min(fc.keys(), key=lambda k: abs(k - self.price_quantile))
            path = fc[q].copy()
            path.iloc[0] = float(history.iloc[-1]) if len(history) else float(price)
            self._plan = solve_day_lp_with_costs(
                path, battery, state, self.costs, dt_h=self.dt_h, note="cost_aware_lp"
            )
            self._plan_day = day_key
        return self._plan.get(ts, Decision(note="unplanned_hour"))


@dataclass
class CostAwarePerfectForesightDaily:
    """Oracle daily LP with ExecutionCosts in the objective (not tradeable)."""

    name: str = "cost_aware_perfect_foresight_daily"
    dt_h: float = 1.0
    costs: ExecutionCosts = field(default_factory=ExecutionCosts)
    _plan: dict[pd.Timestamp, Decision] | None = field(default=None, repr=False)
    _plan_day: str | None = field(default=None, repr=False)

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
        _ = history, price
        if remaining_day_prices is None or remaining_day_prices.empty:
            return Decision(note="no_day_prices")
        day_key = str(ts.tz_convert("Europe/Berlin").date()) if ts.tzinfo else str(pd.Timestamp(ts).date())
        if self._plan is None or self._plan_day != day_key:
            self._plan = solve_day_lp_with_costs(
                remaining_day_prices,
                battery,
                state,
                self.costs,
                dt_h=self.dt_h,
                note="cost_aware_pf",
            )
            self._plan_day = day_key
        return self._plan.get(ts, Decision(note="unplanned_hour"))


@dataclass
class MLCostAwareForecastDrivenLP:
    """ML forecast + cost-aware LP (fees/slippage/degradation in the objective)."""

    name: str = "ml_cost_aware_forecast_driven_lp"
    dt_h: float = 1.0
    lookback_days: int = 90
    refit_every_days: int = 7
    price_quantile: float = 0.50
    use_fundamentals: bool = True
    calibrate: bool = True
    calibrator_kind: str = "rolling"
    mondrian_mode: str = "rl_daily"
    fundamentals: dict | None = field(default=None, repr=False)
    costs: ExecutionCosts = field(default_factory=ExecutionCosts)
    _inner: CostAwareForecastDrivenLP | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if WalkForwardQuantileForecast is None:
            raise ImportError("WalkForwardQuantileForecast is required")
        fc = WalkForwardQuantileForecast(
            lookback_days=self.lookback_days,
            refit_every_days=self.refit_every_days,
            use_fundamentals=self.use_fundamentals,
            calibrate=self.calibrate,
            calibrator_kind=self.calibrator_kind,
            mondrian_mode=self.mondrian_mode,
            fundamentals=self.fundamentals,
        )
        self._inner = CostAwareForecastDrivenLP(
            name=self.name,
            dt_h=self.dt_h,
            forecast=fc,
            price_quantile=self.price_quantile,
            costs=self.costs,
        )

    def decide(self, **kwargs):
        return self._inner.decide(**kwargs)
