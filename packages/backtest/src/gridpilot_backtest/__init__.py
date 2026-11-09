"""GridPilot walk-forward backtest harness (paper trading only)."""
from gridpilot_backtest.costs import (
    COST_SOURCES,
    DEFAULT_COST_SWEEP,
    ExecutionCosts,
    ZERO_COSTS,
    apply_costs_to_actions,
    cost_sensitivity_table,
)
from gridpilot_backtest.equity_plot import equity_and_drawdown_figure
from gridpilot_backtest.harness import BacktestHarness, StrategyResult, comparison_table

__all__ = [
    "BacktestHarness",
    "StrategyResult",
    "comparison_table",
    "ExecutionCosts",
    "ZERO_COSTS",
    "DEFAULT_COST_SWEEP",
    "COST_SOURCES",
    "apply_costs_to_actions",
    "cost_sensitivity_table",
    "equity_and_drawdown_figure",
]
__version__ = "0.2.0"
