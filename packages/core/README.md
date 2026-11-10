> This package now lives in the **GridPilot umbrella**: [`packages/core`](https://github.com/DataWithSyed/gridpilot/tree/main/packages/core). Install the whole project from the repo root with `pip install -e ".[dev]"`.

# gridpilot-core

**Step 1** of [GridPilot](https://github.com/DataWithSyed/gridpilot) — the paper-trading agent runtime.

Battery model (SoC, efficiency, cycles, degradation cost) · strategy interface · **ThresholdArbitrage** + **PerfectForesightDaily** baselines · risk limits / kill switch · Energy-Charts DE-LU day-ahead **replay** · rolling / full-sample **P10 / P50 / P90** daily PnL · event log.

> **Paper trading only.** This repository contains **no** code that places real orders on any exchange.

## Measured results (real run, 2026-08-01 → 2026-10-15)

All figures from `python scripts/run_paper_trade.py --start 2026-08-01 --end 2026-10-15` on 2026-11-10 (Asia/Karachi). Energy-Charts returns 15-min MTUs; this run **resamples to hourly means** and simulates at `dt_h = 1`. Illustrative BESS: **1 MW / 2 MWh**, η 0.95/0.95, SoC 5–95 %, degradation **ASSUMED** 5 €/MWh-throughput, max **2 cycles/day**.

| Fact | Value |
|---|---|
| Hourly bars | **1,824** |
| DA price mean / min / max | **140.48 / −19.00 / 697.31** €/MWh |
| Negative-price share (hourly) | **5.15 %** |
| ThresholdArbitrage final cash | **9,993.05** € |
| Threshold daily PnL mean / P10 / P50 / P90 | **133.24 / 0.00 / 144.73 / 301.47** € |
| PerfectForesightDaily final cash (oracle) | **25,228.43** € |
| PF daily PnL mean / P10 / P50 / P90 | **330.63 / 163.07 / 304.59 / 484.19** € |
| Threshold capture of PF cash | **39.6 %** |
| Kill switch tripped | **no** |

Attribution: [Energy-Charts](https://api.energy-charts.info) (Fraunhofer ISE) / Bundesnetzagentur \| SMARD.de — **CC BY 4.0**.

Machine-readable dump: `results/summary.json`. Narrative: `results/measured_facts.md`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/run_paper_trade.py --start 2026-08-01 --end 2026-10-15
pytest -q
```

Set `GRIDPILOT_SKIP_LIVE=1` to skip live Energy-Charts tests.

## Package layout

```
src/gridpilot_core/
  battery.py       # SoC / power / efficiency / cycles / degradation
  strategy.py      # Strategy protocol + ThresholdArbitrage + PerfectForesightDaily
  risk.py          # RiskLimits, drawdown kill switch, cycle budget
  risk_stats.py    # daily PnL, rolling & full-sample P10/P50/P90
  agent.py         # PaperAgent loop + event log integration
  data_replay.py   # Energy-Charts v2 DE-LU fetch/cache (+ hourly resample)
  events.py        # Append-only EventLog
scripts/run_paper_trade.py
tests/
docs/assumptions.md
docs/limitations.md
```

## Related GridPilot modules

- [gridpilot](https://github.com/DataWithSyed/gridpilot) — umbrella
- [gridpilot-data](https://github.com/DataWithSyed/gridpilot-data) — pluggable live/replay adapters
- [gridpilot-risk](https://github.com/DataWithSyed/gridpilot-risk) — bootstrap VaR/CVaR
- [gridpilot-strategies](https://github.com/DataWithSyed/gridpilot-strategies) — forecast-driven LP (beats threshold by +41.6% cash on the 2026-08-01→2026-10-15 window)

## Related work (not duplicated)

- [gridpilot](https://github.com/DataWithSyed/gridpilot) — umbrella roadmap
- [de-day-ahead-price-forecasting](https://github.com/DataWithSyed/de-day-ahead-price-forecasting) — forecasts to plug into future strategies
- [de-bess-reserve-revenue-stacking](https://github.com/DataWithSyed/de-bess-reserve-revenue-stacking) — reserve stacking (future strategy hook)
- [epm-data-pipeline](https://github.com/DataWithSyed/epm-data-pipeline) — lab panel (same public sources)

## Limitations

See [`docs/limitations.md`](docs/limitations.md). Short version: paper trading only; hourly DA; oracle strategy is not tradeable; P50/P90 are empirical daily-PnL percentiles, not a full VaR engine.

## Licence

MIT for code. Upstream data keep their own licences — always attribute.
