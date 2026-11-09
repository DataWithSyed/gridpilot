# Assumptions (`gridpilot-core`)

| ID | Assumption | Default | Source / note |
|---|---|---|---|
| A1 | One-way charge / discharge efficiency | 0.95 / 0.95 | ASSUMED round-trip ≈ 90 %; typical Li-ion inverter+pack band |
| A2 | SoC operating band | 5–95 % | ASSUMED residual / headroom; asset-specific |
| A3 | Degradation cost | 5 €/MWh throughput | ASSUMED order-of-magnitude wear proxy; set 0 to disable |
| A4 | Threshold lookback | 168 h | ASSUMED one trading week |
| A5 | Threshold quantiles | P25 / P75 | ASSUMED; tunable |
| A6 | Min actionable spread | 10 €/MWh | ASSUMED vs fees/noise |
| A7 | Max cycles / day | 2.0 | ASSUMED warranty-style budget |
| A8 | Illustrative BESS | 1 MW / 2 MWh | Demo sizing only |

Label any new numeric default **ASSUMED** with a one-line rationale when you change this table.
