# Related DataWithSyed repos (linked, not duplicated)

| Repo | What it already does | How GridPilot differs / reuses |
|---|---|---|
| [de-day-ahead-price-forecasting](https://github.com/DataWithSyed/de-day-ahead-price-forecasting) | LEAR / GBM / ensemble DE-LU price forecasts + BESS value of forecast | `gridpilot-forecast` will adapt forecasts into the agent; not a second bake-off study |
| [de-bess-reserve-revenue-stacking](https://github.com/DataWithSyed/de-bess-reserve-revenue-stacking) | DA + FCR/aFRR LP stacking | GridPilot is an agent loop + risk layer; reserve stacking is a future strategy hook |
| [de-wind-probabilistic-forecasting](https://github.com/DataWithSyed/de-wind-probabilistic-forecasting) | Wind P50/P90-style quantiles + conformal | Optional renewable feature input later |
| [epm-data-pipeline](https://github.com/DataWithSyed/epm-data-pipeline) / [eu-power-market-lab](https://github.com/DataWithSyed/eu-power-market-lab) | Lab-grade public panel + roadmap | `packages/data` may reuse panels; owns live/replay adapters for the agent |
| [bess-lcos-montecarlo-irr](https://github.com/DataWithSyed/bess-lcos-montecarlo-irr) | LCOS / IRR / Monte Carlo | Project finance ≠ trading agent |


GridPilot `packages/forecast` reuses ideas from the DE day-ahead and wind probabilistic repos without copying their full data stacks.

## Optional reserve / FCR overlay (link only)

GridPilot does **not** co-optimise FCR/aFRR here. For a reserve-revenue stacking formulation on German BESS, see
[de-bess-reserve-revenue-stacking](https://github.com/DataWithSyed/de-bess-reserve-revenue-stacking) — treat it as a future strategy hook / overlay, not a duplicated LP in this repo.

