"""Paper-trading execution costs: fees, slippage, battery degradation.

Paper trading only — never places real orders. All defaults are ASSUMED and
labelled with public source ranges (see ``COST_SOURCES``).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from gridpilot_backtest.metrics import historical_cvar, max_drawdown, summarise
from gridpilot_backtest.fees import (
    ASSUMED_DEGRADATION_EUR_PER_MWH,
    ECC_DA_CLEARING_EUR_PER_MWH,
    FEE_CATALOG,
    catalog_dicts,
    sourced_preset_components,
)

# Crossref-checked / public sources for ASSUMED ranges (not fabricated point estimates).
COST_SOURCES = [
    {
        "id": "A-C1",
        "item": "Trading fee EUR/MWh",
        "assumed_default": 0.05,
        "range_eur_mwh": [0.04, 0.10],
        "note": (
            "Order-of-magnitude from historical EPEX SPOT published trading fees "
            "(DE-AT-CH Day-Ahead Auction ~0.04 €/MWh; continuous intraday ~0.10 €/MWh "
            "in older public price lists). Current member fee schedules change; treat as ASSUMED."
        ),
        "source": "EPEX SPOT public price lists / fee documentation (no DOI)",
        "doi": None,
    },
    {
        "id": "A-C2",
        "item": "Slippage / bid-ask proxy EUR/MWh",
        "assumed_default": 0.50,
        "range_eur_mwh": [0.0, 2.0],
        "note": (
            "Day-ahead SDAC is a single clearing price (no classic bid-ask). This term is an "
            "ASSUMED conservatism for imperfect fills / modelling error when paper-trading "
            "against the published clearing series. Set 0 for pure auction-fill assumption."
        ),
        "source": "Modelling choice (ASSUMED); not an exchange fee",
        "doi": None,
    },
    {
        "id": "A-C3",
        "item": "Battery degradation EUR/MWh throughput",
        "assumed_default": 5.0,
        "range_eur_mwh": [1.0, 10.0],
        "note": (
            "Linear wear proxy already used in gridpilot-core BatteryConfig. Order-of-magnitude "
            "aligned with cycling/degradation cost discussion in grid-storage arbitrage literature."
        ),
        "source": "Kies et al. (2018) joint arbitrage–degradation framing; NREL ATB cost context",
        "doi": "10.1088/1742-6596/977/1/012005",
    },
]


@dataclass(frozen=True)
class ExecutionCosts:
    """Per-MWh paper execution costs applied to simulated fills.

    Sign convention matches ``PaperAgent``: charge buys (pays price), discharge sells.
    Slippage worsens both sides: buy at ``price + slippage``, sell at ``price - slippage``.
    Fee and degradation apply to throughput ``grid_in + grid_out`` (MWh).
    """

    fee_eur_per_mwh: float = 0.05
    slippage_eur_per_mwh: float = 0.50
    degradation_eur_per_mwh: float = 5.0
    label: str = "base"

    def __post_init__(self) -> None:
        for name in ("fee_eur_per_mwh", "slippage_eur_per_mwh", "degradation_eur_per_mwh"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.label == "sourced":
            d["assumed"] = False
            d["cost_basis"] = "sourced"
            d["still_assumed"] = ["degradation_eur_per_mwh"]
            d["is_lower_bound_on_exchange_fees"] = True
            d["fee_composition"] = {
                "ecc_da_clearing_eur_per_mwh": ECC_DA_CLEARING_EUR_PER_MWH,
                "epex_trading_eur_per_mwh": None,
            }
            d["sources"] = catalog_dicts()
        else:
            d["assumed"] = self.label not in {"zero"}
            d["cost_basis"] = "zero" if self.label == "zero" else "assumed"
            d["sources"] = COST_SOURCES
        return d


ZERO_COSTS = ExecutionCosts(
    fee_eur_per_mwh=0.0,
    slippage_eur_per_mwh=0.0,
    degradation_eur_per_mwh=0.0,
    label="zero",
)

# Previous default: all three legs ASSUMED (A-C1–A-C3). Kept as the "base" label.
ASSUMED_BASE_COSTS = ExecutionCosts(
    fee_eur_per_mwh=0.05,
    slippage_eur_per_mwh=0.50,
    degradation_eur_per_mwh=ASSUMED_DEGRADATION_EUR_PER_MWH,
    label="base",
)

# Sourced DA preset: ECC 0.015 €/MWh clearing only; DA slippage 0; degradation still ASSUMED.
# EPEX trading fee is omitted because it is not in the current public price list (lower bound).
SOURCED_COSTS = ExecutionCosts(
    fee_eur_per_mwh=ECC_DA_CLEARING_EUR_PER_MWH,
    slippage_eur_per_mwh=0.0,
    degradation_eur_per_mwh=ASSUMED_DEGRADATION_EUR_PER_MWH,
    label="sourced",
)

# Named sweep used by the long-window net-of-costs evaluation.
DEFAULT_COST_SWEEP: tuple[ExecutionCosts, ...] = (
    ZERO_COSTS,
    ExecutionCosts(0.05, 0.0, 5.0, label="fee_deg"),
    ASSUMED_BASE_COSTS,
    ExecutionCosts(0.10, 1.0, 10.0, label="stress"),
    SOURCED_COSTS,
)

_PRESETS = {
    "zero": ZERO_COSTS,
    "assumed": ASSUMED_BASE_COSTS,
    "base": ASSUMED_BASE_COSTS,
    "sourced": SOURCED_COSTS,
}


def get_cost_preset(name: str) -> ExecutionCosts:
    """Return a named cost preset (``assumed`` / ``base``, ``sourced``, or ``zero``)."""
    key = (name or "").strip().lower()
    if key not in _PRESETS:
        known = ", ".join(sorted(_PRESETS))
        raise ValueError(f"Unknown cost preset {name!r}. Known: {known}")
    return _PRESETS[key]


def apply_costs_to_actions(
    actions: pd.DataFrame,
    costs: ExecutionCosts,
    *,
    initial_cash_eur: float = 0.0,
) -> dict[str, Any]:
    """Reprice paper fills under ``costs`` without re-running the strategy.

    Requires columns: ``ts``, ``price``, ``grid_in_mwh``, ``grid_out_mwh``.
    Strategies are unchanged (ex-ante decisions); this is an accounting layer only.
    """
    if actions is None or len(actions) == 0:
        eq = pd.Series(dtype=float, name="equity_eur")
        daily = pd.Series(dtype=float)
        return {
            "equity_eur": eq,
            "daily": daily,
            "final_cash_eur": float(initial_cash_eur),
            "total_fees_eur": 0.0,
            "total_slippage_eur": 0.0,
            "total_degradation_eur": 0.0,
            "throughput_mwh": 0.0,
            "metrics": summarise(daily, eq, initial_cash_eur, 0.0, False),
            "costs": costs.to_dict(),
        }

    df = actions.copy()
    if "ts" in df.columns:
        df = df.sort_values("ts")
        idx = pd.DatetimeIndex(pd.to_datetime(df["ts"]))
    else:
        idx = pd.RangeIndex(len(df))

    price = df["price"].astype(float).to_numpy()
    gin = df["grid_in_mwh"].astype(float).fillna(0.0).to_numpy()
    gout = df["grid_out_mwh"].astype(float).fillna(0.0).to_numpy()
    thr = gin + gout

    buy_px = price + costs.slippage_eur_per_mwh
    sell_px = price - costs.slippage_eur_per_mwh
    step_mtm = -gin * buy_px + gout * sell_px
    step_fee = thr * costs.fee_eur_per_mwh
    step_deg = thr * costs.degradation_eur_per_mwh
    # Slippage vs mid: gin*slip + gout*slip
    step_slip = thr * costs.slippage_eur_per_mwh

    cash_path = initial_cash_eur + np.cumsum(step_mtm - step_fee - step_deg)
    equity = pd.Series(cash_path, index=idx, name="equity_eur")
    # Daily PnL from end-of-day equity (Berlin calendar if tz-aware)
    if getattr(equity.index, "tz", None) is not None:
        day_key = equity.index.tz_convert("Europe/Berlin").date
    else:
        day_key = pd.DatetimeIndex(equity.index).date
    # last equity per day, then diff
    by_day = equity.groupby(day_key).last()
    daily = by_day.diff()
    if len(daily):
        daily.iloc[0] = float(by_day.iloc[0] - initial_cash_eur)
    daily = daily.astype(float)

    cycles = float("nan")
    if "soc" in df.columns and len(df):
        # Prefer cycles from agent summary when available; leave NaN here
        pass

    metrics = summarise(
        daily,
        equity,
        float(cash_path[-1]) if len(cash_path) else float(initial_cash_eur),
        float(cycles) if np.isfinite(cycles) else float("nan"),
        False,
    )
    return {
        "equity_eur": equity,
        "daily": daily,
        "final_cash_eur": float(cash_path[-1]) if len(cash_path) else float(initial_cash_eur),
        "total_fees_eur": float(step_fee.sum()),
        "total_slippage_eur": float(step_slip.sum()),
        "total_degradation_eur": float(step_deg.sum()),
        "throughput_mwh": float(thr.sum()),
        "metrics": metrics,
        "costs": costs.to_dict(),
    }


def cost_sensitivity_table(
    actions_by_strategy: dict[str, pd.DataFrame],
    sweep: tuple[ExecutionCosts, ...] = DEFAULT_COST_SWEEP,
    *,
    cycles_by_strategy: dict[str, float] | None = None,
    killed_by_strategy: dict[str, bool] | None = None,
    oracle_name: str = "perfect_foresight_daily",
) -> pd.DataFrame:
    """Build a long table: one row per (strategy, cost scenario)."""
    cycles_by_strategy = cycles_by_strategy or {}
    killed_by_strategy = killed_by_strategy or {}
    rows: list[dict[str, Any]] = []
    for label_costs in sweep:
        priced = {
            name: apply_costs_to_actions(acts, label_costs)
            for name, acts in actions_by_strategy.items()
        }
        pf = priced.get(oracle_name, {}).get("final_cash_eur")
        for name, res in priced.items():
            m = dict(res["metrics"])
            m["strategy"] = name
            m["cost_scenario"] = label_costs.label
            m["fee_eur_per_mwh"] = label_costs.fee_eur_per_mwh
            m["slippage_eur_per_mwh"] = label_costs.slippage_eur_per_mwh
            m["degradation_eur_per_mwh"] = label_costs.degradation_eur_per_mwh
            m["total_fees_eur"] = res["total_fees_eur"]
            m["total_slippage_eur"] = res["total_slippage_eur"]
            m["total_degradation_eur"] = res["total_degradation_eur"]
            m["throughput_mwh"] = res["throughput_mwh"]
            m["cycles"] = float(cycles_by_strategy.get(name, m.get("cycles", float("nan"))))
            m["killed"] = bool(killed_by_strategy.get(name, False))
            m["capture_vs_pf_pct"] = (
                100.0 * m["final_cash_eur"] / pf if pf not in (None, 0) else None
            )
            rows.append(m)
    return pd.DataFrame(rows)
