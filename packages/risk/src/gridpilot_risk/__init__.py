"""GridPilot risk engine — scenario PnL, VaR/CVaR, limit hooks (paper trading)."""
from gridpilot_risk.bootstrap import block_bootstrap_daily_paths, scenario_revenue_distribution
from gridpilot_risk.var_cvar import historical_var, historical_cvar, distribution_summary
from gridpilot_risk.limits import RiskLimitSpec, KillSwitch, enforce_limits

__all__ = [
    "block_bootstrap_daily_paths",
    "scenario_revenue_distribution",
    "historical_var",
    "historical_cvar",
    "distribution_summary",
    "RiskLimitSpec",
    "KillSwitch",
    "enforce_limits",
]
__version__ = "0.1.0"
