# GridPilot

**Open paper-trading agent stack for electricity markets** — live/near-live public data, pluggable charge/discharge strategies, risk limits, probabilistic P50/P90 outcome tracking, forecasting hooks, and backtests.

GridPilot is a **multi-repo** system. This umbrella holds architecture, roadmap, and docs. Executable code lives in the module repos.

> **Paper trading only.** Nothing in GridPilot places real orders on any power exchange or broker. There is no live execution path in the public code.

## Why this exists

Battery storage and flexible demand need an **agent loop**: observe the market → forecast → decide under risk limits → simulate fills → learn. Prior single-repo studies under [@DataWithSyed](https://github.com/DataWithSyed) already cover forecasting, reserve stacking, LCOS, and lab data. GridPilot **links** those ideas into a coherent agent architecture instead of duplicating them.

## Architecture

```mermaid
flowchart TB
  subgraph data [gridpilot-data]
    EC[Energy-Charts DE-LU DA<br/>CC BY 4.0]
    ENTSO[ENTSO-E optional<br/>token via env]
    Replay[Replay / cache]
  end

  subgraph core [gridpilot-core]
    Batt[Battery SoC / η / cycles]
    StratIF[Strategy interface]
    RiskCore[Risk limits + kill switch]
    Paper[Paper-trading loop]
    Pctl[Rolling P50 / P90 PnL]
    Log[Event log]
  end

  subgraph brain [Decision modules]
    FC[gridpilot-forecast]
    STR[gridpilot-strategies]
    RSK[gridpilot-risk]
  end

  subgraph eval [Evaluation]
    BT[gridpilot-backtest]
    UI[gridpilot-dashboard]
  end

  EC --> Replay
  ENTSO --> Replay
  Replay --> Paper
  Batt --> Paper
  StratIF --> Paper
  RiskCore --> Paper
  Paper --> Log
  Paper --> Pctl
  FC --> StratIF
  STR --> StratIF
  RSK --> RiskCore
  Paper --> BT
  BT --> UI
  Pctl --> UI
```

## Roadmap

- [x] **Umbrella** (`gridpilot`): architecture, methods, assumptions, contributing *(this repo)*
- [x] **Core runtime** ([`gridpilot-core`](https://github.com/DataWithSyed/gridpilot-core)): battery · strategies · paper loop · Energy-Charts replay · risk limits · P50/P90
- [x] **Data adapters** ([`gridpilot-data`](https://github.com/DataWithSyed/gridpilot-data)): Energy-Charts live/near-live + replay + optional ENTSO-E env-token adapter
- [ ] **Forecasting** (`gridpilot-forecast`): price / renewable probabilistic forecasts (links `de-day-ahead-price-forecasting`, `de-wind-probabilistic-forecasting`)
- [x] **Risk engine** ([`gridpilot-risk`](https://github.com/DataWithSyed/gridpilot-risk)): block-bootstrap scenario PnL, VaR / CVaR, limit hooks
- [x] **Strategy pack** ([`gridpilot-strategies`](https://github.com/DataWithSyed/gridpilot-strategies)): forecast-driven + risk-aware LP (reserve-stacking hooks still planned)
- [ ] **Backtest harness** (`gridpilot-backtest`): walk-forward reports with P50/P90
- [ ] **Dashboard** (`gridpilot-dashboard`): Streamlit ops view

## Measured results so far (real runs)

Window **2026-08-01 → 2026-10-15**, DE-LU day-ahead via Energy-Charts (CC BY 4.0), 15-min → hourly means, illustrative **1 MW / 2 MWh** BESS. Paper trading only; no fees/slippage.

| Module | Highlight |
|---|---|
| [`gridpilot-core`](https://github.com/DataWithSyed/gridpilot-core) | Threshold cash **9,993** € (39.6% of PF oracle **25,228** €); daily PnL P50 **144.73** € |
| [`gridpilot-data`](https://github.com/DataWithSyed/gridpilot-data) | **1,824** hourly bars; DA mean **140.48** €/MWh; **5.15%** negative hours |
| [`gridpilot-risk`](https://github.com/DataWithSyed/gridpilot-risk) | Daily VaR₅% / CVaR₅% (threshold) **70.36 / 150.37** €; 21-day bootstrap cash P50 **2,499** € (40 paths) |
| [`gridpilot-strategies`](https://github.com/DataWithSyed/gridpilot-strategies) | **ForecastDrivenLP** cash **14,145** € (**+41.6%** vs threshold; **56.1%** of PF); RiskAware cuts daily CVaR₅% to **3.92** € |

Honest caveat: forecast is rolling hour-of-day quantile climatology (not ML); early days are lookback warm-up; risk-aware is a return/risk trade-off, not strictly dominant on cash.

## Quick start (core)

```bash
git clone https://github.com/DataWithSyed/gridpilot-core.git
cd gridpilot-core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/run_paper_trade.py --start 2026-08-01 --end 2026-10-15
pytest -q
```

## Related work

See [`docs/related-work.md`](docs/related-work.md). Highlights:

- [de-day-ahead-price-forecasting](https://github.com/DataWithSyed/de-day-ahead-price-forecasting)
- [de-bess-reserve-revenue-stacking](https://github.com/DataWithSyed/de-bess-reserve-revenue-stacking)
- [epm-data-pipeline](https://github.com/DataWithSyed/epm-data-pipeline) · [eu-power-market-lab](https://github.com/DataWithSyed/eu-power-market-lab)
- [bess-lcos-montecarlo-irr](https://github.com/DataWithSyed/bess-lcos-montecarlo-irr)

## Docs

- [`docs/methods.md`](docs/methods.md) — literature anchors (DOIs)
- [`docs/assumptions.md`](docs/assumptions.md) — labelled ASSUMED defaults
- [`docs/limitations.md`](docs/limitations.md) — honest scope limits
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to help
- [`docs/issue-templates/`](docs/issue-templates/) — bug / feature templates

## Licence

MIT for code and documentation in this umbrella. Upstream market data keep their own licences — always attribute (Energy-Charts / SMARD, and others as added).
