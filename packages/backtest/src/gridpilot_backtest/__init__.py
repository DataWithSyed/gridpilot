"""GridPilot walk-forward backtest harness (paper trading only)."""
from gridpilot_backtest.costs import (
    ASSUMED_BASE_COSTS,
    COST_SOURCES,
    DEFAULT_COST_SWEEP,
    ExecutionCosts,
    SOURCED_COSTS,
    ZERO_COSTS,
    apply_costs_to_actions,
    cost_sensitivity_table,
    get_cost_preset,
)
from gridpilot_backtest.equity_plot import equity_and_drawdown_figure
from gridpilot_backtest.fees import FEE_CATALOG, RETRIEVAL_DATE, sourced_preset_components
from gridpilot_backtest.harness import BacktestHarness, StrategyResult, comparison_table

__all__ = [
    "BacktestHarness",
    "StrategyResult",
    "comparison_table",
    "ExecutionCosts",
    "ZERO_COSTS",
    "ASSUMED_BASE_COSTS",
    "SOURCED_COSTS",
    "DEFAULT_COST_SWEEP",
    "COST_SOURCES",
    "FEE_CATALOG",
    "RETRIEVAL_DATE",
    "apply_costs_to_actions",
    "cost_sensitivity_table",
    "get_cost_preset",
    "sourced_preset_components",
    "equity_and_drawdown_figure",
]
__version__ = "0.3.0"
