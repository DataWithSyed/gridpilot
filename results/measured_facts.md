# Measured walk-forward facts

Date: 2026-11-10 (Asia/Karachi). Window: 2026-08-01 → 2026-10-15. Source: Energy-Charts DE-LU day-ahead (CC BY 4.0), 15-min MTU resampled to hourly means. Battery: 1 MW / 2 MWh, η 0.95/0.95, SoC 5–95 %, degradation ASSUMED 5 €/MWh-throughput, max 2 cycles/day. Paper trading only; no fees/slippage.

| Strategy | Final cash € | Capture of PF % | vs threshold % | Daily P10 | Daily P50 | Daily P90 | CVaR5% loss € |
|---|---|---|---|---|---|---|---|
| ThresholdArbitrage | 9993.05 | 39.6 | 100.0 | 0.00 | 144.73 | 301.47 | 150.37 |
| ForecastDrivenLP | 14145.42 | 56.1 | 141.6 | 20.86 | 183.10 | 354.14 | 16.74 |
| RiskAwareForecastLP | 10107.12 | 40.1 | 101.1 | 0.00 | 113.83 | 310.17 | 3.92 |
| PerfectForesightDaily | 25228.43 | 100.0 | 252.5 | 163.07 | 304.59 | 484.19 | −105.32 |

Forecast = rolling 28-day hour-of-day quantile climatology (not ML). See `walk_forward.json`.
