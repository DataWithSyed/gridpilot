# Limitations (`gridpilot-core`)

- **Paper trading only.** This package never places, routes, or signs orders on any exchange or broker. There is no live execution path.
- **Day-ahead prices only (v0.1).** Intraday continuous, balancing energy, and reserve markets are out of scope here (see roadmap in the umbrella repo).
- **Hourly MTU.** Energy-Charts DE-LU series used here are treated as hourly; quarter-hour scheduling is future work.
- **Oracle strategy is not tradeable.** `PerfectForesightDaily` sees the full day's prices; use it only as an upper-bound benchmark.
- **Threshold strategy is naive.** Rolling quantiles ignore forecasts, imbalance risk, and fees/taxes.
- **Degradation** is a constant EUR/MWh-throughput ASSUMED proxy (`BatteryConfig.degradation_eur_per_mwh`), not a chemistry model.
- **Risk P50/P90** are empirical percentiles of *daily paper PnL* over the backtest window / rolling windows — not predictive VaR under a fitted return model (that lands in `gridpilot-risk`).
- **Data licence.** Only CC BY bidding zones are accepted. Attribute Energy-Charts.info / SMARD.de.
- **No secrets.** Optional future ENTSO-E access will use an env var only; nothing is shipped in this repo.
