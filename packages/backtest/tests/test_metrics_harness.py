"""Backtest metrics / harness unit tests (synthetic, no network)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from gridpilot_backtest.harness import BacktestHarness, StrategyResult, comparison_table
from gridpilot_backtest.metrics import historical_cvar, max_drawdown, summarise


def test_max_drawdown_and_cvar():
    eq = pd.Series([0, 10, 5, 12, 4], index=pd.date_range("2026-01-01", periods=5, freq="D"))
    assert max_drawdown(eq) == 8.0  # peak 12 -> 4
    daily = pd.Series([-100.0, -50.0, 10.0, 20.0, -80.0])
    c = historical_cvar(daily, 0.05)
    assert c > 0


def test_comparison_table():
    results = {
        "a": StrategyResult("a", {"final_cash_eur": 50, "daily_pnl_p10": 0, "daily_pnl_p50": 1,
                                  "daily_pnl_p90": 2, "cvar_5pct_loss_daily": 3,
                                  "max_drawdown_eur": 4, "cycles": 1, "killed": False, "n_days": 2}),
        "perfect_foresight_daily": StrategyResult(
            "perfect_foresight_daily",
            {"final_cash_eur": 100, "daily_pnl_p10": 0, "daily_pnl_p50": 1,
             "daily_pnl_p90": 2, "cvar_5pct_loss_daily": 3,
             "max_drawdown_eur": 4, "cycles": 1, "killed": False, "n_days": 2},
        ),
    }
    t = comparison_table(results)
    assert float(t.loc[t.strategy == "a", "capture_vs_pf_pct"].iloc[0]) == 50.0


@dataclass
class _FakeRes:
    daily: pd.Series
    equity_eur: pd.Series
    summary: dict


class _FakeAgent:
    def __init__(self, batt, strat, risk):
        self.strat = strat

    def run(self, prices):
        eq = prices.cumsum() * 0 + 100.0
        eq.iloc[-1] = 100.0 + float(getattr(self.strat, "bump", 0))
        daily = pd.Series([1.0, 2.0, getattr(self.strat, "bump", 0)], index=pd.date_range("2026-01-01", periods=3, freq="D"))
        return _FakeRes(daily=daily, equity_eur=eq, summary={
            "final_cash_eur": float(eq.iloc[-1]), "total_cycles": 1.0, "killed": False
        })


def test_harness_runs():
    class S:
        name = "x"
        bump = 10

    h = BacktestHarness(
        battery_factory=lambda: None,
        risk_factory=lambda: None,
        agent_factory=lambda b, s, r: _FakeAgent(b, s, r),
    )
    prices = pd.Series(range(10), index=pd.date_range("2026-01-01", periods=10, freq="h", tz="UTC"))
    out = h.run(prices, {"x": S()})
    assert out["x"].metrics["final_cash_eur"] == 110.0
