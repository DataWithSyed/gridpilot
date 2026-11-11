# FAQ

**Paper trading only.** Nothing in this repository places or routes real orders.

## Is GridPilot a live trading system?

No. There is no exchange or broker adapter that submits orders. The live package is a **near-live paper pilot**: it fetches public Energy-Charts prices, locks an ex-ante schedule, and records paper fills. The simulator is a tick replay of the same paper loop.

## Can I point this at EPEX or another venue?

Not with the public code. Adding signed order routing is out of scope (see [CONTRIBUTING.md](../CONTRIBUTING.md)). The sourced fee table is for **paper accounting**, not a membership or connectivity guide.

## Where do the headline numbers come from?

From committed result files produced by scripts in this repo. The front-page table in the [README](../README.md) is a summary; the full tables, windows, and file links are in [RESULTS.md](RESULTS.md). Do not invent or update a figure without a new script run.

## Are all 12-month cash figures comparable?

No. The published **cost-aware ML 65,473 €** path uses fundamentals features, rolling CQR, and `PaperAgent` cycle clips (**411** cycles, **8,735** h). The gate-closure, ID, and CVaR experiments on the same calendar window use other fans or clip settings (and sometimes **8,736** h). [RESULTS.md](RESULTS.md) labels each comparison. Do not substitute a bid-curve lock (for example 75,102 €, unclipped) for the published ML path.

## Why is P10–P90 coverage still below 80%?

The nominal interval is 80%. On the 12-month window, raw coverage was **50.0%**, rolling CQR **72.2%**, and tight Mondrian **78.9%** — still slightly short. The 14-day live pilot (re-run 2026-11-10) printed **52.4%**. Better calibration has also **not** automatically raised paper profit (tight Mondrian cash was slightly below rolling cost-aware ML).

## Why did bid curves lose money versus the locked schedule?

On the same fan, quantile and anchored curves **under-cycled** (about 151–188 cycles versus 458–479 on the locked price-taking schedule) and every 90% CI on the daily gap excluded zero. The result is documented as a **negative** finding in [BIDDING.md](BIDDING.md). It is not hidden or relabelled as a win.

## What does “proxy-only” mean for the intraday result?

Energy-Charts has **no public ID or ID-index series** (checked 2026-11-10). Official reBAP was **not fetchable** without Netztransparenz OAuth. The published layer therefore sets ID and reBAP **equal to the realised DA price** (`PROXY_ID_EQ_DA`, `PROXY_REBAP_EQ_DA`). The +23,015 € / +63.23 €/day figure measures the value of **reshaping after DA publication** assuming ID trades occur at DA, with no ID–DA spread. It is not a measured ID-index or official reBAP backtest. See [INTRADAY.md](INTRADAY.md).

## Which fees are sourced and which are assumed?

The default **sourced** preset is ECC Lux DA **clearing 0.015 €/MWh** (ECC Price List 085b, 2 Nov 2026), DA slippage **0** (SDAC single clearing price), and degradation still **ASSUMED 5 €/MWh**. The current EPEX trading fee was not in the public 2026 price list and is omitted (lower bound). Details and citations: [fees.md](fees.md).

## How do I run it locally?

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ui]"
pytest -q
gridpilot-sim run --scenario normal --speed 0 --seed 0
gridpilot-sim dashboard
```

Docker and more commands are in the [README](../README.md) quickstart and [SIMULATOR.md](SIMULATOR.md).

## Why is there no GitHub Actions workflow?

This project’s org token cannot push `.github/workflows`. Issue templates live under [`docs/issue-templates/`](issue-templates/). Run `pytest -q` locally.

## Do you claim real-money performance or a star-count goal?

No. Paper cash is not live P&L. Star counts are not a project goal in these docs.
