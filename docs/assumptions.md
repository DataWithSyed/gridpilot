# Cross-cutting assumptions

See also `gridpilot-core/docs/assumptions.md` for runtime defaults.

| ID | Item | Note |
|---|---|---|
| U1 | Paper trading | No live order placement in any module |
| U2 | Primary price feed (v0) | Energy-Charts DE-LU day-ahead, CC BY 4.0 |
| U3 | ENTSO-E | Optional; `ENTSOE_API_TOKEN` env var only; not required for core replay |
| U4 | P50 / P90 | Empirical percentiles of scenario or rolling daily PnL unless a module states a parametric model |
| U5 | Fees / taxes / imbalance | ASSUMED zero in core v0.1 unless a strategy adds them |


## Forecasting package (ASSUMED)

| ID | Assumption | Value / note | Source |
|---|---|---|---|
| A-F1 | LEAR-lite feature set | Price lags D-1/D-2/D-7 + calendar (no TSO forecasts) | Simplified vs Lago et al. 2021 / de-day-ahead-price-forecasting |
| A-F2 | Quantile GBM hyperparams | lr 0.08, max_iter 120, max_leaf_nodes 15 | Chosen for short-sample stability / box memory |
| A-F3 | Ensemble weights | Equal mean of LEAR point and GBM quantiles | Same convention as de-day-ahead-price-forecasting |
| A-F4 | Lookback / refit | 45-day rolling train; refit every 3 days in measured run | ASSUMED compute tradeoff |
| A-F5 | Compact LEAR mode | When n_samples ≤ n_features, per-hour compact lag design + AIC noise_variance | Required for identifiable LassoLarsIC on short windows |
