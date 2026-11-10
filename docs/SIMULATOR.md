# GridPilot real-time paper simulator

**Paper trading only.** This package replays or synthesises day-ahead prices and feeds the GridPilot agent with information that would have been available at each moment. It does **not** connect to an exchange, does **not** place or route orders, and its P&L is **not** real-money performance.

## What a buyer can demonstrate

- Tick-by-tick replay of historical DE-LU day-ahead prices (Energy-Charts / SMARD, CC BY 4.0) or **clearly labelled synthetic** scenario packs, at adjustable speed (`--speed 1`, `60`, `1000`; `0` = as fast as possible).
- Day-ahead **gate closure at 12:00 Europe/Berlin (CET/CEST) on D-1**. The schedule for delivery day D is locked then, on a forecast built from history **strictly before** that instant. Realised D prices are used only for settlement. There is **no lookahead**.
- The same paper agent loop used in the rest of the project: hour-of-day P10/P50/P90 fan, **cost-aware LP** with the **sourced** fee preset (ECC DA clearing 0.015 €/MWh, DA slippage 0, degradation still ASSUMED 5 €/MWh — see [`docs/fees.md`](fees.md)), battery SoC / power / efficiency / cycle limits, and a drawdown **kill switch**.
- Paper fills update SoC and cumulative **gross and net** P&L against a threshold baseline and a **labelled perfect-foresight oracle** (the oracle *does* use lookahead; the agent never sees it).
- Live Streamlit dashboard (price, forecast fan, SoC, decisions, P&L, risk / kill-switch events) plus a JSON/CSV run and an exportable HTML/PNG demo report.
- Deterministic **seeded** synthetic runs; scenario packs: `normal`, `price_spike`, `negative_prices`, `data_outage`, `forecast_failure`.

## Agent policies

`--policy` selects what is locked at 12:00 Europe/Berlin on D-1 (paper only):

| Policy | Behaviour |
| --- | --- |
| `cost_aware` (default) | Cost-aware LP on the climatology P50 path (original behaviour). |
| `quantile_bids` | P10/P50/P90 SDAC-style curves, cleared at the realised price with partial acceptance. |
| `cvar` | Cost-aware CVaR LP on the last 60 causal daily paths (`--cvar-lambda`, default 2). |
| `id_reopt` | Lock the cost-aware DA plan at gate closure, then re-optimise at 13:00 D-1 once DA prices are public. ID mid is the **PROXY_ID_EQ_DA** label (Energy-Charts has no public ID series). Tick cash still uses the DA fee preset. |

See [`docs/BIDDING.md`](BIDDING.md), [`docs/INTRADAY.md`](INTRADAY.md), [`docs/CVAR.md`](CVAR.md) for the 12-month backtests and honest limitations.

```bash
gridpilot-sim run --scenario normal --policy cvar --cvar-lambda 2 --seed 0
```

## How to run

From the umbrella repo root:

```bash
pip install -e ".[dev,ui]"
gridpilot-sim run --scenario normal --speed 0 --seed 0
gridpilot-sim run --scenario price_spike --speed 1000 --seed 1
gridpilot-sim run --scenario historical --speed 0          # uses the Energy-Charts cache if present
gridpilot-sim dashboard                                   # Streamlit UI of the last run
./packages/simulator/scripts/quickstart.sh
```

Docker (one command, still paper-only):

```bash
docker build -t gridpilot-sim -f packages/simulator/Dockerfile .
docker run --rm -p 8502:8502 gridpilot-sim
```

## Honest limitations

| Topic | What is true |
| --- | --- |
| Money | **Paper P&L only.** Never a claim of live or real-money performance. |
| Connectivity | No EPEX, ECC, TSO, or broker API. No order tickets. |
| Market | **Day-ahead only.** No continuous intraday, no SIDC IDAs, no imbalance (reBAP) cash-out. |
| Fees | The default preset is the **sourced** catalog in [`docs/fees.md`](fees.md): ECC clearing 0.015 €/MWh is official; the current EPEX trading fee is **not** in the public Price List Guide (omitted — lower bound); degradation **5 €/MWh is still ASSUMED**; fixed membership fees are disclosed but not amortised. |
| Forecast | Default demo forecast is a causal hour-of-day climatology with residual P10/P90, not the full walk-forward ML used in the 12-month backtest (that model is heavier). |
| Gate closure | 12:00 Europe/Berlin on D-1 is the SDAC gate time used here. Exact publication timestamps of historical DA prices are not simulated minute-by-minute. |
| Battery | Same illustrative 1 MW / 2 MWh, η 0.95/0.95, SoC 5–95% assumptions as the rest of GridPilot. |
| Synthetic data | `normal`, `price_spike`, `negative_prices`, `data_outage`, and `forecast_failure` are **synthetic and labelled**. Do not present them as market results. |

If you are evaluating this as a product demo, treat it as a **research and sales sandbox** for the agent loop, not as a trading system that is ready to send orders.
