"""Tests for execution costs and equity figure."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridpilot_backtest.costs import (
    DEFAULT_COST_SWEEP,
    ExecutionCosts,
    ZERO_COSTS,
    apply_costs_to_actions,
    cost_sensitivity_table,
)
from gridpilot_backtest.equity_plot import equity_and_drawdown_figure


def _toy_actions(n: int = 48) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="Europe/Berlin")
    price = np.linspace(50, 150, n)
    gin = np.zeros(n)
    gout = np.zeros(n)
    gin[::4] = 1.0
    gout[2::4] = 1.0
    return pd.DataFrame(
        {"ts": idx, "price": price, "grid_in_mwh": gin, "grid_out_mwh": gout, "soc": 0.5}
    )


def test_zero_costs_match_mid_mtm():
    acts = _toy_actions()
    z = apply_costs_to_actions(acts, ZERO_COSTS)
    # Manual mid MTM
    cash = 0.0
    for _, r in acts.iterrows():
        cash += -r.grid_in_mwh * r.price + r.grid_out_mwh * r.price
    assert z["final_cash_eur"] == pytest.approx(cash, rel=1e-9)
    assert z["total_fees_eur"] == 0.0


def test_fees_and_slippage_reduce_cash():
    acts = _toy_actions()
    z = apply_costs_to_actions(acts, ZERO_COSTS)["final_cash_eur"]
    base = apply_costs_to_actions(acts, ExecutionCosts(0.05, 0.5, 5.0))["final_cash_eur"]
    assert base < z
    stress = apply_costs_to_actions(acts, ExecutionCosts(0.1, 1.0, 10.0))["final_cash_eur"]
    assert stress < base


def test_cost_sensitivity_table_shape():
    acts = {"a": _toy_actions(), "perfect_foresight_daily": _toy_actions()}
    tbl = cost_sensitivity_table(acts, DEFAULT_COST_SWEEP)
    assert len(tbl) == len(DEFAULT_COST_SWEEP) * 2
    assert set(tbl["cost_scenario"]) >= {"zero", "base", "stress"}


def test_equity_figure_writes(tmp_path: Path):
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    eqs = {
        "threshold": pd.Series(np.cumsum(np.ones(30)), index=idx),
        "ml": pd.Series(np.cumsum(np.linspace(1, 2, 30)), index=idx),
    }
    out = equity_and_drawdown_figure(eqs, outfile=tmp_path / "eq.png")
    assert out is not None and out.exists() and out.stat().st_size > 0
