"""Run multiple strategies on one price series and build a comparison table."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from gridpilot_backtest.metrics import summarise


@dataclass
class StrategyResult:
    name: str
    metrics: dict
    daily: pd.Series | None = None
    equity: pd.Series | None = None


@dataclass
class BacktestHarness:
    """Walk-forward style: one causal run per strategy over the full window.

    Strategies that use forecasts must themselves be ex-ante (GridPilot ML /
    climatology strategies already are). This harness does not peek.
    """

    battery_factory: Callable[[], Any]
    risk_factory: Callable[[], Any]
    agent_factory: Callable[[Any, Any, Any], Any]
    results: dict[str, StrategyResult] = field(default_factory=dict)

    def run(self, prices: pd.Series, strategies: dict[str, Any]) -> dict[str, StrategyResult]:
        self.results = {}
        for name, strat in strategies.items():
            batt = self.battery_factory()
            risk = self.risk_factory()
            agent = self.agent_factory(batt, strat, risk)
            res = agent.run(prices)
            m = summarise(
                res.daily,
                res.equity_eur,
                float(res.summary["final_cash_eur"]),
                float(res.summary.get("total_cycles", float("nan"))),
                bool(res.summary.get("killed", False)),
            )
            self.results[name] = StrategyResult(name=name, metrics=m, daily=res.daily, equity=res.equity_eur)
        return self.results


def comparison_table(results: dict[str, StrategyResult], oracle_name: str = "perfect_foresight_daily") -> pd.DataFrame:
    rows = []
    oracle = results.get(oracle_name)
    pf = oracle.metrics["final_cash_eur"] if oracle else None
    for name, r in results.items():
        m = dict(r.metrics)
        m["strategy"] = name
        m["capture_vs_pf_pct"] = (100.0 * m["final_cash_eur"] / pf) if pf else None
        rows.append(m)
    cols = [
        "strategy",
        "final_cash_eur",
        "capture_vs_pf_pct",
        "daily_pnl_p10",
        "daily_pnl_p50",
        "daily_pnl_p90",
        "cvar_5pct_loss_daily",
        "max_drawdown_eur",
        "cycles",
        "killed",
    ]
    return pd.DataFrame(rows)[cols]
