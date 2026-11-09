"""Strategy interface and two baseline paper-trading strategies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from gridpilot_core.battery import BatteryConfig, BatteryState


@dataclass(frozen=True)
class Decision:
    charge_mw: float = 0.0
    discharge_mw: float = 0.0
    note: str = ""


class Strategy(Protocol):
    name: str

    def decide(
        self,
        *,
        ts: pd.Timestamp,
        price: float,
        history: pd.Series,
        battery: BatteryConfig,
        state: BatteryState,
        remaining_day_prices: pd.Series | None = None,
    ) -> Decision: ...


@dataclass
class ThresholdArbitrage:
    """Charge below rolling low quantile, discharge above rolling high quantile.

    Ex-ante: uses only prices up to and including the current bar for quantiles
    (causal). No foresight of future prices.
    """

    name: str = "threshold_arbitrage"
    lookback_hours: int = 168  # ASSUMED 7-day rolling window
    low_q: float = 0.25
    high_q: float = 0.75
    min_spread_eur: float = 10.0  # ASSUMED minimum high-low gap to act

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
        _ = remaining_day_prices
        window = history.dropna().iloc[-self.lookback_hours :]
        if len(window) < max(24, self.lookback_hours // 4):
            return Decision(note="warmup")
        lo = float(window.quantile(self.low_q))
        hi = float(window.quantile(self.high_q))
        if hi - lo < self.min_spread_eur:
            return Decision(note="spread_too_small")
        if price <= lo and state.soc < battery.soc_max - 1e-9:
            return Decision(charge_mw=battery.power_mw, note=f"price<={lo:.2f}")
        if price >= hi and state.soc > battery.soc_min + 1e-9:
            return Decision(discharge_mw=battery.power_mw, note=f"price>={hi:.2f}")
        return Decision(note="hold")


@dataclass
class PerfectForesightDaily:
    """Daily LP with perfect knowledge of the day's prices (ex-post upper bound).

    Solves a day-ahead LP at the first interval of each calendar day, then
    replays the planned schedule. This is **not** a tradeable strategy; it is
    the oracle benchmark used for capture-ratio reporting.

    Decision variables are grid energy (MWh) per interval; power bounds use dt_h.
    """

    name: str = "perfect_foresight_daily"
    dt_h: float = 1.0
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
        _ = history, price
        if remaining_day_prices is None or remaining_day_prices.empty:
            return Decision(note="no_day_prices")
        day_key = str(ts.tz_convert("Europe/Berlin").date()) if ts.tzinfo else str(pd.Timestamp(ts).date())
        if self._plan is None or self._plan_day != day_key:
            self._plan = self._solve_day(remaining_day_prices, battery, state)
            self._plan_day = day_key
        return self._plan.get(ts, Decision(note="unplanned_hour"))

    def _solve_day(
        self,
        prices: pd.Series,
        battery: BatteryConfig,
        state: BatteryState,
    ) -> dict[pd.Timestamp, Decision]:
        """Maximise revenue − degradation subject to SoC / power / one-day horizon."""
        prices = prices.astype(float)
        T = len(prices)
        if T == 0:
            return {}
        # Decision vars: [c_0..c_{T-1}, d_0..d_{T-1}] in MWh grid
        # SoC dynamics in energy (MWh stored): e_{t+1} = e_t + eta_c * c_t - d_t / eta_d
        n = 2 * T
        c_price = prices.to_numpy()
        # Objective: minimise cost = sum(price * c - price * d) + deg*(c+d)
        # → linprog minimises; revenue = -cost without deg
        deg = battery.degradation_eur_per_mwh
        c_obj = np.concatenate([c_price + deg, -c_price + deg])

        e0 = state.soc * battery.energy_mwh
        e_min = battery.soc_min * battery.energy_mwh
        e_max = battery.soc_max * battery.energy_mwh
        emax = battery.power_mw * self.dt_h  # MWh per interval

        # Bounds on grid energy per interval
        bounds = [(0.0, emax)] * T + [(0.0, emax)] * T

        # Equality: terminal SoC free within band via inequalities only.
        # Inequalities for SoC path: e_min <= e0 + sum_{k=0..t}(eta_c c - d/eta_d) <= e_max
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

        res = linprog(
            c_obj,
            A_ub=np.asarray(A_ub),
            b_ub=np.asarray(b_ub),
            bounds=bounds,
            method="highs",
        )
        plan: dict[pd.Timestamp, Decision] = {}
        if not res.success:
            for ts in prices.index:
                plan[ts] = Decision(note=f"lp_fail:{res.message}")
            return plan
        x = res.x
        for i, ts in enumerate(prices.index):
            c_mwh = float(x[i])
            d_mwh = float(x[T + i])
            # Convert interval energy back to average MW over dt_h
            scale = 1.0 / self.dt_h if self.dt_h > 0 else 0.0
            plan[ts] = Decision(
                charge_mw=c_mwh * scale,
                discharge_mw=d_mwh * scale,
                note="pf_lp",
            )
        return plan
