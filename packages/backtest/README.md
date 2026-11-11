# gridpilot-backtest (umbrella package)

Walk-forward backtest harness for GridPilot strategies.

> Part of [gridpilot](https://github.com/DataWithSyed/gridpilot) under `packages/backtest`.

```bash
python -m gridpilot_backtest.cli --start 2026-08-01 --end 2026-10-15
# or
python packages/backtest/src/gridpilot_backtest/cli.py
pytest -q packages/backtest
```

Paper trading only. Energy-Charts / SMARD — CC BY 4.0.

## Costs and equity

`gridpilot_backtest.costs.ExecutionCosts` applies ASSUMED fee/slippage/degradation to paper fills. `equity_plot.equity_and_drawdown_figure` writes `figures/equity_curve_net.png`.


## Documentation

Part of the [GridPilot umbrella](../../README.md). Guides, methods, and measured paper results: [`docs/index.md`](../../docs/index.md). Paper trading only — no exchange connectivity and no real-money claims.
