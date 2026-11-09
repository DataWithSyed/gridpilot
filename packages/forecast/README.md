# gridpilot-forecast (umbrella package)

Probabilistic **day-ahead DE-LU price** forecasting for GridPilot paper trading.

> Lives under the [gridpilot](https://github.com/DataWithSyed/gridpilot) umbrella as `packages/forecast`. Not a separate GitHub repository.

## Models

| Model | Role |
|---|---|
| Naive | Lago-style D-1 / D-7 benchmark |
| LEAR-lite | 24 hourly LassoLarsIC on asinh-scaled **price lags + calendar** |
| Quantile GBM | `HistGradientBoostingRegressor` with quantile loss → P10 / P50 / P90 |
| Ensemble | Mean of LEAR point and GBM quantiles (equal weights, ASSUMED) |

Ideas linked from [de-day-ahead-price-forecasting](https://github.com/DataWithSyed/de-day-ahead-price-forecasting) and conformal ideas from [de-wind-probabilistic-forecasting](https://github.com/DataWithSyed/de-wind-probabilistic-forecasting) — **not a copy** of those pipelines.

### Honest limitations

- **Price-only features** in this package (no TSO load/solar/wind day-ahead forecasts). The prior DE forecast repo uses those and is stronger; we link it instead of duplicating the data stack.
- Short demo window (Aug–mid Oct 2026) → limited train history; ML may not beat the rolling hour-of-day climatology in `gridpilot-strategies`.
- Paper trading only. No orders to any exchange.

## Install (from umbrella clone)

```bash
pip install -e packages/forecast
pip install -e ../gridpilot-core ../gridpilot-strategies   # sibling checkouts
pytest -q packages/forecast
python packages/forecast/scripts/run_forecast_eval.py
```

## Licence

MIT. Market data: Energy-Charts / SMARD — CC BY 4.0.
