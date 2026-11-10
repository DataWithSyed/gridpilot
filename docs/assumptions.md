# Cross-cutting assumptions

See also `gridpilot-core/docs/assumptions.md` for runtime defaults.

| ID | Item | Note |
|---|---|---|
| U1 | Paper trading | No live order placement in any module |
| U2 | Primary price feed (v0) | Energy-Charts DE-LU day-ahead, CC BY 4.0 |
| U3 | ENTSO-E | Optional; `ENTSOE_API_TOKEN` env var only; not required for core replay |
| U4 | P50 / P90 | Empirical percentiles of scenario or rolling daily PnL unless a module states a parametric model |
| U5 | Fees / taxes / imbalance | Paper cost layer in `packages/backtest` (`ExecutionCosts`); see A-C1–A-C3 |


## Forecasting package (ASSUMED)

| ID | Assumption | Value / note | Source |
|---|---|---|---|
| A-F1 | LEAR-lite feature set | Price lags D-1/D-2/D-7 + calendar (no TSO forecasts) | Simplified vs Lago et al. 2021 / de-day-ahead-price-forecasting |
| A-F2 | Quantile GBM hyperparams | lr 0.08, max_iter 120, max_leaf_nodes 15 | Chosen for short-sample stability / box memory |
| A-F3 | Ensemble weights | Equal mean of LEAR point and GBM quantiles | Same convention as de-day-ahead-price-forecasting |
| A-F4 | Lookback / refit | 45-day rolling train; refit every 3 days in measured run | ASSUMED compute tradeoff |
| A-F5 | Compact LEAR mode | When n_samples ≤ n_features, per-hour compact lag design + AIC noise_variance | Required for identifiable LassoLarsIC on short windows |


## Paper execution costs (`packages/backtest`, ASSUMED)

| ID | Item | Default | Range | Source |
|---|---|---:|---|---|
| A-C1 | Trading fee €/MWh | 0.05 | 0.04–0.10 | Historical EPEX SPOT public trading-fee order-of-magnitude (no DOI) |
| A-C2 | Slippage / fill conservatism €/MWh | 0.50 | 0–2 | Modelling choice; DA auction has a single clearing price |
| A-C3 | Degradation €/MWh throughput | 5.0 | 1–10 | Order-of-magnitude; DOI [10.1088/1742-6596/977/1/012005](https://doi.org/10.1088/1742-6596/977/1/012005) (Crossref-checked) |

Cost accounting is applied to paper fills; strategies are **not** re-optimised for fees in this release.
Conformal calibration refs (Crossref-checked): Lei et al. DOI [10.1080/01621459.2017.1307116](https://doi.org/10.1080/01621459.2017.1307116); Mondrian inductive CP DOI [10.1007/s10994-018-5754-9](https://doi.org/10.1007/s10994-018-5754-9).


## Cost-aware dispatch (2026-11-10)

The paper LP can put fee + slippage + degradation in the objective (`packages/forecast` `solve_day_lp_with_costs`) so schedules **re-optimise** rather than only paying costs after fills. Defaults remain A-C1–A-C3. Tight Mondrian regimes (hour bucket × hourly residual-load tercile × hour-of-day volatility) fall back to parent labels when a cell has fewer than 5 days in the calibration window.
