# gridpilot-data

**Step 2** of [GridPilot](https://github.com/DataWithSyed/gridpilot) — pluggable market-data adapters for **paper trading**.

- `EnergyChartsAdapter` — live / near-live DE-LU day-ahead prices + DE public power (CC BY 4.0)
- `ReplayAdapter` — offline replay from CSV / Parquet / Series
- `EntsoeAdapter` — optional ENTSO-E prices via **`ENTSOE_API_TOKEN`** env var (never hardcoded)

> **Paper trading only.** This repository contains **no** code that places real orders.

## Measured sample (real fetch/cache, 2026-08-01 → 2026-10-15)

From `python scripts/fetch_sample.py` on 2026-11-10 (Asia/Karachi). Energy-Charts 15-min MTU **resampled to hourly means**.

| Fact | Value |
|---|---|
| Hourly bars | **1,824** |
| DA mean / min / max | **140.48 / −18.995 / 697.31** €/MWh |
| Negative-price share | **5.15 %** |

Attribution: [Energy-Charts](https://api.energy-charts.info) / Bundesnetzagentur | SMARD.de — **CC BY 4.0**.

Machine-readable: `results/sample_summary.json`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
# optional live sample:
GRIDPILOT_SKIP_LIVE=0 python scripts/fetch_sample.py --start 2026-08-01 --end 2026-10-15
```

Optional ENTSO-E: `pip install 'gridpilot-data[entsoe]'` and export `ENTSOE_API_TOKEN`.

## Tests

**8 passed**, 1 skipped (live) with `GRIDPILOT_SKIP_LIVE=1`.

## Limitations

See [`docs/limitations.md`](docs/limitations.md).

## Licence

MIT for code. Upstream data keep their own licences — always attribute.
