# gridpilot-risk

**Step 4** of [GridPilot](https://github.com/DataWithSyed/gridpilot) — scenario risk engine for paper trading.

- Moving-**block bootstrap** of daily DE price paths → scenario revenue distribution (P10/P50/P90)
- Historical **VaR / CVaR**
- SoC / cycle / drawdown **limit hooks** + kill switch (compatible with `gridpilot-core`)

> **Paper trading only.** No real orders.

## Measured results (2026-11-10, Asia/Karachi)

Prices: Energy-Charts DE-LU, 2026-08-01 → 2026-10-15, hourly resample. Strategy: `ThresholdArbitrage` on a 1 MW / 2 MWh BESS (same defaults as core).

### Full-window daily PnL risk (75 days)

| Metric | Value |
|---|---|
| Daily PnL P10 / P50 / P90 | **0.00 / 144.73 / 301.47** € |
| Historical VaR 5% (as loss) | **70.36** €/day |
| Historical CVaR 5% (as loss) | **150.37** €/day |
| Final cash (point run) | **9,993.05** € |

### Block-bootstrap scenario cash (40 paths × 21 days, block=7)

Toy? No — each scenario runs the real `PaperAgent` + `ThresholdArbitrage`.

| Metric | Value |
|---|---|
| Scenario cash P10 / P50 / P90 | **1,719 / 2,499 / 3,372** € |
| Mean scenario cash | **2,508** € |

Negative VaR-as-loss on the bootstrap cash distribution means the left tail is still profitable over 21-day paths (quantile of cash > 0). See `results/real_risk_summary.json`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python scripts/run_bootstrap_demo.py
```

## Tests

**6 passed**.

## Limitations

See [`docs/limitations.md`](docs/limitations.md).

## Licence

MIT.
