import pandas as pd

from gridpilot_core.agent import PaperAgent
from gridpilot_core.battery import BatteryConfig
from gridpilot_core.risk import RiskLimits
from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage


def _prices(n_days=5):
    idx = pd.date_range("2026-08-01", periods=n_days * 24, freq="h", tz="Europe/Berlin")
    # Daily shape: cheap night, expensive evening
    vals = []
    for h in range(n_days * 24):
        hour = h % 24
        vals.append(20.0 if hour < 6 else (80.0 if hour >= 18 else 40.0))
    return pd.Series(vals, index=idx, name="da_price_eur_mwh")


def test_perfect_foresight_makes_money():
    prices = _prices(3)
    agent = PaperAgent(
        BatteryConfig(degradation_eur_per_mwh=0.0),
        PerfectForesightDaily(),
        RiskLimits(max_cycles_per_day=3.0, max_drawdown_eur=1e9),
    )
    res = agent.run(prices)
    assert res.summary["final_cash_eur"] > 0
    assert res.summary["total_cycles"] > 0


def test_threshold_runs_without_crash():
    prices = _prices(10)
    agent = PaperAgent(
        BatteryConfig(),
        ThresholdArbitrage(lookback_hours=48, low_q=0.3, high_q=0.7, min_spread_eur=5.0),
        RiskLimits(max_drawdown_eur=1e9),
    )
    res = agent.run(prices)
    assert res.summary["n_hours"] == len(prices)
    assert "daily_pnl_p50_eur" in res.summary
