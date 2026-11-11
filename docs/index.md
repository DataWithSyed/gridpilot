# GridPilot documentation

Index of design notes, methods, and measured paper-trading results. Start with the [umbrella README](../README.md) for a one-page overview.

**Paper trading only.** Nothing in this repository places or routes real orders. Figures are backtests or a near-live paper pilot, not real-money performance.

## Guides

| Page | What it covers |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Package responsibilities, data flow, and key classes |
| [METHODOLOGY.md](METHODOLOGY.md) | Forecast features, CQR, cost-aware and CVaR LPs, SDAC timing, bootstrap CIs |
| [RESULTS.md](RESULTS.md) | All measured tables, windows, and links to source files |
| [fees.md](fees.md) | Sourced vs assumed execution costs (retrieval 2026-11-10) |
| [BIDDING.md](BIDDING.md) | SDAC-style gate-closure bid curves (honest negative vs locked schedule) |
| [INTRADAY.md](INTRADAY.md) | Post-DA re-optimisation; ID and reBAP proxies |
| [CVAR.md](CVAR.md) | Cost-aware CVaR LP and return-versus-CVaR frontier |
| [SIMULATOR.md](SIMULATOR.md) | Paper market simulator (CLI, dashboard, Docker) |
| [GLOSSARY.md](GLOSSARY.md) | BESS, SDAC, P50/P90, CVaR, reBAP, and related terms |
| [FAQ.md](FAQ.md) | Short answers to common questions |
| [assumptions.md](assumptions.md) | Labelled ASSUMED defaults |
| [limitations.md](limitations.md) | Scope limits |
| [methods.md](methods.md) | Literature DOI anchors |
| [related-work.md](related-work.md) | Related public repos under @DataWithSyed |
| [CHANGELOG.md](../CHANGELOG.md) | Project history from git |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to help (paper trading only; no secrets) |
| [issue-templates/](issue-templates/) | Bug and feature templates (no `.github/workflows`) |

## Packages

Each package has its own README that links back here:

- [`packages/core`](../packages/core/README.md)
- [`packages/data`](../packages/data/README.md)
- [`packages/forecast`](../packages/forecast/README.md)
- [`packages/risk`](../packages/risk/README.md)
- [`packages/strategies`](../packages/strategies/README.md)
- [`packages/backtest`](../packages/backtest/README.md)
- [`packages/live`](../packages/live/README.md)
- [`packages/simulator`](../packages/simulator/README.md)
- [`packages/dashboard`](../packages/dashboard/README.md)

## Licence

MIT for code and documentation. Energy-Charts / SMARD market data remain [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — always attribute.
