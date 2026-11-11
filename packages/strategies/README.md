> This package now lives in the **GridPilot umbrella**: [`packages/strategies`](https://github.com/DataWithSyed/gridpilot/tree/main/packages/strategies). Install the whole project from the repo root with `pip install -e ".[dev]"`.

# gridpilot-strategies

**Step 5** of [GridPilot](https://github.com/DataWithSyed/gridpilot) — strategy pack for paper trading.

- `ForecastDrivenLP` — rolling P50 hour-of-day quantile forecast → daily LP (re-optimised each hour)
- `RiskAwareForecastLP` — pessimistic P10/P50 blend forecast path → LP
- Walk-forward evaluation vs `ThresholdArbitrage` and `PerfectForesightDaily` from `gridpilot-core`

> **Paper trading only.** No real orders.

## Measured walk-forward (real prices, 2026-08-01 → 2026-10-15)

1 MW / 2 MWh BESS, η 0.95/0.95, max 2 cycles/day, degradation ASSUMED 5 €/MWh-throughput. Hourly resample of Energy-Charts 15-min MTU. Forecast = rolling 28-day hour-of-day climatology (**not** ML). Run: 2026-11-10 Asia/Karachi.

| Strategy | Final cash | vs threshold | Capture of PF | Daily P10 / P50 / P90 | CVaR₅% loss (daily) |
|---|---|---|---|---|---|
| ThresholdArbitrage | **9,993** € | 100% | 39.6% | 0.00 / 144.73 / 301.47 | 150.37 |
| **ForecastDrivenLP** | **14,145** € | **141.6%** | **56.1%** | 20.86 / 183.10 / 354.14 | 16.74 |
| RiskAwareForecastLP | **10,107** € | 101.1% | 40.1% | 0.00 / 113.83 / 310.17 | **3.92** |
| PerfectForesightDaily (oracle) | **25,228** € | 252.5% | 100% | 163.07 / 304.59 / 484.19 | −105.32* |

\* Negative CVaR-as-loss means the left tail of daily PnL is still positive (oracle almost never loses money on a day).

**Honest takeaway:** the simple forecast-driven LP **beats** the threshold baseline (+41.6% cash) and roughly halves left-tail daily loss vs threshold, but still captures only **56%** of the perfect-foresight oracle. The risk-aware blend is close to threshold on cash while cutting CVaR hard — a risk/return trade-off, not a free lunch.

Machine-readable: `results/walk_forward.json`.

## Quick start

```bash
pip install -e ../gridpilot-core -e ".[dev]"
pytest -q
python scripts/walk_forward_eval.py --start 2026-08-01 --end 2026-10-15
```

## Tests

**3 passed** (unit). Full walk-forward is the integration measurement above.

## Limitations

See [`docs/limitations.md`](../../docs/limitations.md). Short version: climatology forecast, warm-up days, no fees/slippage, paper only.

## Licence

MIT. Upstream prices: Energy-Charts / SMARD — CC BY 4.0.


## Documentation

Part of the [GridPilot umbrella](../../README.md). Guides, methods, and measured paper results: [`docs/index.md`](../../docs/index.md). Paper trading only — no exchange connectivity and no real-money claims.
