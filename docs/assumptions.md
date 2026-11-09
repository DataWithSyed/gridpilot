# Cross-cutting assumptions

See also `gridpilot-core/docs/assumptions.md` for runtime defaults.

| ID | Item | Note |
|---|---|---|
| U1 | Paper trading | No live order placement in any module |
| U2 | Primary price feed (v0) | Energy-Charts DE-LU day-ahead, CC BY 4.0 |
| U3 | ENTSO-E | Optional; `ENTSOE_API_TOKEN` env var only; not required for core replay |
| U4 | P50 / P90 | Empirical percentiles of scenario or rolling daily PnL unless a module states a parametric model |
| U5 | Fees / taxes / imbalance | ASSUMED zero in core v0.1 unless a strategy adds them |
