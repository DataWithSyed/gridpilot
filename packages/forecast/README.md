# gridpilot-forecast (umbrella package)

Probabilistic **day-ahead DE-LU price** forecasting for GridPilot paper trading.

> Lives under the [gridpilot](https://github.com/DataWithSyed/gridpilot) umbrella as `packages/forecast`. Not a separate GitHub repository.

## Models

| Model | Role |
|---|---|
| Naive | Lago-style D-1 / D-7 benchmark |
| LEAR-lite | 24 hourly LassoLarsIC on asinh-scaled **price lags + calendar** (+ optional day-ahead fundamentals) |
| Quantile GBM | `HistGradientBoostingRegressor` quantile loss → P10 / P50 / P90 |
| Ensemble | Mean of LEAR point and GBM quantiles (equal weights, ASSUMED) |
| Rolling CQR | Conformalised P10–P90 band (delay-aware; ideas linked from `de-wind-probabilistic-forecasting`) |

### Fundamentals (ex-ante)

Day-ahead TSO forecasts of **load / solar / wind** from Energy-Charts `public_power_forecast` (CC BY 4.0) enter residual-load features for delivery day D. Same-day realised prices never enter features (leakage tests in `tests/`). If day-ahead forecasts are unavailable, lagged actuals (D-1) may be used and must be labelled.

### Measured (real run 2025-11-01 → 2026-10-30)

- Ensemble + fundamentals MAE **16.26** €/MWh vs naive **33.98** (337–340 days)
- Raw 80% interval coverage **50.0%** → CQR **72.2%** (still short of nominal 80% — honest gap)
- Reliability after CQR: P10 **8.8%**, P50 **40.7%**, P90 **81.0%** (nominal 10/50/90)

## Install (from umbrella clone)

```bash
pip install -e packages/forecast
pip install -e ../gridpilot-core ../gridpilot-strategies
pytest -q packages/forecast
# optional rebuild of gitignored cache (rate-limited API):
python packages/forecast/scripts/fetch_fundamentals.py --start 2025-11-01 --end 2026-10-30
python packages/forecast/scripts/run_long_window_eval.py
```

## Licence

MIT. Market data: Energy-Charts / SMARD — CC BY 4.0.

## Mondrian CQR + costs eval

`scripts/run_costs_mondrian_equity.py` compares rolling vs Mondrian CQR coverage and writes net-of-cost backtests (paper only).
