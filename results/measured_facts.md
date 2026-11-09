# Measured risk facts

Date: 2026-11-10 (Asia/Karachi). Prices: Energy-Charts DE-LU 2026-08-01 → 2026-10-15 hourly. Strategy under test: ThresholdArbitrage (gridpilot-core defaults).

## Full-window daily PnL (75 days)

- P10 / P50 / P90: 0.00 / 144.73 / 301.47 €
- VaR 5% (loss): 70.36 €/day
- CVaR 5% (loss): 150.37 €/day
- Final cash: 9993.05 €

## Block bootstrap (40 scenarios × 21 days, block length 7)

Each path runs PaperAgent + ThresholdArbitrage.

- Scenario cash P10 / P50 / P90: 1718.86 / 2499.37 / 3371.74 €
- Mean: 2508.44 €

See `real_risk_summary.json`.
