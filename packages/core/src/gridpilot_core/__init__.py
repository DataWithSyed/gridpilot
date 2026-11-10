"""gridpilot-core: paper-trading BESS agent runtime (no live order placement)."""

__version__ = "0.1.0"

from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_core.risk import RiskLimits, RiskManager
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage
from gridpilot_core.agent import PaperAgent, AgentResult

__all__ = [
    "__version__",
    "BatteryConfig",
    "BatteryState",
    "RiskLimits",
    "RiskManager",
    "PerfectForesightDaily",
    "ThresholdArbitrage",
    "PaperAgent",
    "AgentResult",
]
