# Results

All figures below were produced by scripts in this repository and are copied from committed result files or the README entries that those files support. Nothing here is a new run. **Paper trading only — not real-money performance.**

Primary historical window unless noted: **2025-11-01 → 2026-10-30**, DE-LU day-ahead, Energy-Charts CC BY 4.0, illustrative **1 MW / 2 MWh** BESS. Some tables use **8,735** hours and some later same-window experiments use **8,736** hours (364 days; spring/fall DST cancel). The one-hour difference is labelled per table and the series are not mixed when comparing policies.

## 1. Market snapshot (12-month window)

Source: README / fundamentals + CQR backtest (`packages/forecast/results/long_window_eval.json`, `packages/forecast/results/costs_mondrian_equity.json`).

| Metric | Value |
| --- | --- |
| Hours / DA mean | **8,735** h · **110.88** €/MWh (min −499 · max 697.31 · **5.17%** negative) |
| Forecast MAE | Ensemble + fundamentals **16.26** vs naive **33.98** €/MWh |
| 80% coverage | Raw **50.0%** → rolling CQR **72.2%** → Mondrian CQR **78.2%** (nominal 80%; still short) |
| Reliability (Mondrian) | P10 **8.2%** · P50 **46.5%** · P90 **86.4%** (rolling CQR was 8.8 / 40.7 / 81.0) |

## 2. Accounting-only net of assumed costs (fee 0.05 / slip 0.50 / deg 5)

Strategies are **not** re-optimised for fees in this table. Source: `packages/forecast/results/costs_mondrian_equity.json` and the README entry dated 2026-11-10.

| Strategy (net of base costs) | Final cash € | Capture of PF | Daily PnL P10 / P50 / P90 € | CVaR₅% loss € | Max DD € | Δ€/day vs thr. (90% CI) |
|---|---:|---:|---|---:|---:|---|
| Threshold | 31,944 | 44.2% | −61.74 / 76.78 / 247.22 | 175.43 | 309 | — |
| ForecastDrivenLP (climatology) | 33,932 | 47.0% | −54.25 / 51.62 / 300.21 | 178.83 | 434 | +5.5 [−5.5, 15.9] *(CI crosses 0)* |
| RiskAwareForecastLP (climatology) | 26,860 | 37.2% | −5.59 / 26.01 / 238.50 | 114.29 | 455 | −14.0 [−25.0, −4.5] |
| **MLForecastDrivenLP** (fund+rolling CQR) | **57,153** | **79.2%** | 0.00 / 135.30 / 362.07 | 79.79 | 466 | **+69.3 [53.3, 82.1]** |
| ML MondrianForecastDrivenLP | 55,501 | 76.9% | −5.48 / 125.88 / 363.69 | 81.99 | 460 | +64.7 [49.2, 79.0] |
| MLRiskAwareForecastLP | 45,566 | 63.1% | 0.00 / 93.47 / 292.63 | **43.06** | 455 | +37.4 [25.1, 48.1] |
| Perfect foresight (oracle) | 72,192 | 100% | 26.91 / 177.22 / 396.57 | 9.23 | 495 | +110.6 [91.7, 124.9] |

**Gross (zero fee/slip/deg):** threshold **36,334** € · ML **68,822** € · Mondrian-ML **67,508** € · PF **85,231** €.

**Cost sensitivity (ML vs threshold final cash €):**

| Scenario | fee / slip / deg | Threshold | ML | ML / thr |
|---|---|---:|---:|---:|
| zero | 0 / 0 / 0 | 36,334 | 68,822 | **1.89×** |
| fee_deg | 0.05 / 0 / 5 | 32,340 | 58,204 | **1.80×** |
| **base** | **0.05 / 0.50 / 5** | **31,944** | **57,153** | **1.79×** |
| stress | 0.10 / 1.0 / 10 | 27,555 | 45,483 | **1.65×** |

Figures: [`packages/backtest/figures/equity_curve_net.png`](../packages/backtest/figures/equity_curve_net.png), [`packages/backtest/figures/coverage_calibration.png`](../packages/backtest/figures/coverage_calibration.png).

Mondrian improved coverage (72.2 → 78.2%) but Mondrian-calibrated ML cash was slightly **below** rolling-CQR ML (55,501 vs 57,153). Calibration quality ≠ automatic PnL gain.

## 3. Cost-aware LP + tight Mondrian (assumed costs, same window)

Source: `packages/forecast/results/cost_aware_tight_mondrian.json` (assumed-cost re-run, 2026-11-10). Coverage on this re-run: raw 50.0% → rolling 72.2% → residual-load Mondrian 76.6% (this re-run) / 78.2% (prior published) → **tight Mondrian 78.9%**. Tight-CQR P50 MAE **16.07** vs rolling **16.26** vs naive **33.98** €/MWh. Reliability (tight Mondrian): P10 **7.8%** · P50 **46.8%** · P90 **86.8%**.

| Strategy (net of base costs) | Final cash € | Capture of cost-aware PF | Throughput MWh | CVaR₅% loss € | Δ€/day vs threshold (90% CI) | Δ€/day vs non-reopt ML (90% CI) |
|---|---:|---:|---:|---:|---|---|
| Threshold (unchanged path) | 31,944 | 39.3% | 791 | 175.43 | — | −69.3 [−82.1, −53.3] |
| ML, accounting-only (not re-optimised) | 57,153 | 70.3% | 2,103 | 79.79 | +69.3 [53.3, 82.1] | — |
| **ML cost-aware LP** (rolling CQR) | **64,646** | **79.5%** | 1,612 | **11.11** | **+89.8 [75.5, 103.7]** | **+20.6 [14.6, 27.6]** |
| ML cost-aware + tight Mondrian | 64,487 | 79.3% | 1,680 | 30.87 | +89.4 [75.5, 103.7] | +20.1 [14.1, 27.8] |
| PF, accounting-only | 72,192 | 88.8% | 2,349 | 9.23 | +110.6 [91.7, 124.9] | +41.3 [33.7, 47.3] |
| **Cost-aware PF** (oracle) | **81,314** | **100%** | 1,947 | — | +135.6 [117.6, 151.0] | +66.4 [57.4, 74.6] |

Re-optimising for costs **improved** net cash (57,153 → 64,646; +20.6 €/day, CI excludes 0). Tight Mondrian **improved coverage** but **did not improve P&L** versus rolling cost-aware ML (64,487 vs 64,646).

## 4. Sourced fee preset (headline 12-month comparison)

Retrieval 2026-11-10. Source: [`docs/fees.md`](fees.md), `packages/forecast/results/sourced_fees_backtest.json`. Window **8,735** h. Cost-aware strategies re-run under sourced costs (fee 0.015 / slip 0 / deg still ASSUMED 5).

| Strategy (net of sourced costs) | Final cash € | Capture of cost-aware PF | Throughput MWh | CVaR₅% loss € | Δ€/day vs threshold (90% CI) | Δ€/day vs non-reopt ML (90% CI) |
|---|---:|---:|---:|---:|---|---|
| Threshold (unchanged path) | 32,367 | 39.3% | 791 | 174.25 | — | −71.2 [−84.0, −55.3] |
| ML, accounting-only (not re-optimised) | 58,277 | 70.8% | 2,103 | 75.88 | +71.2 [55.3, 84.0] | — |
| **ML cost-aware LP** (rolling CQR) | **65,473** | **79.6%** | 1,644 | **13.07** | **+90.9 [76.6, 104.7]** | **+19.8 [13.8, 26.7]** |
| ML cost-aware + tight Mondrian | 65,312 | 79.4% | 1,706 | 28.75 | +90.5 [76.5, 104.6] | +19.3 [13.3, 26.7] |
| PF, accounting-only | 73,449 | 89.3% | 2,349 | 5.48 | +112.9 [93.9, 127.1] | +41.7 [34.1, 47.6] |
| **Cost-aware PF** (oracle) | **82,271** | **100%** | 1,972 | — | +137.1 [119.0, 152.7] | +65.9 [57.0, 73.9] |

Cost-aware ML paid **€8,219** degradation vs **€25** fees under this preset. This is the headline “cost-aware ML vs threshold vs perfect foresight” comparison.

## 5. Gate-closure bid curves (negative result)

Source: [`packages/forecast/results/GATE_CLOSURE_BIDDING.md`](../packages/forecast/results/GATE_CLOSURE_BIDDING.md), `packages/forecast/results/gate_closure_bidding.json`. Window **8,736** h, 364 days, sourced fees, 2026-11-10. Same-fan comparison only. The ML schedule here is **price-only and unclipped** (479.4 cycles) and is **not** a re-run of the 65,473 EUR path (411 cycles, fundamentals + PaperAgent clips).

| Forecast | Locked schedule € | Quantile bids € | Anchored bids € | Bids − schedule €/day (90% CI) |
|---|---:|---:|---:|---|
| 90-day hour-of-day climatology | 60,379 | 13,082 | 17,740 | quantile **−129.94 [−149.98, −107.28]**; anchored **−117.14 [−139.04, −94.56]** |
| Walk-forward ML + tight Mondrian (price-only) | 75,102 | 3,566 | 22,867 | quantile **−196.53 [−222.03, −171.41]**; anchored **−143.50 [−163.33, −122.56]** |

**Did not improve.** Every CI excludes 0. Curves under-cycle (151–188 vs 458–479 cycles). Design: [BIDDING.md](BIDDING.md).

## 6. Post-DA re-optimisation — proxy-only

Source: [`packages/forecast/results/INTRADAY_IMBALANCE.md`](../packages/forecast/results/INTRADAY_IMBALANCE.md). Same climatology DA lock as the bidding study (60,379 EUR). **PROXY_ID_EQ_DA** and **PROXY_REBAP_EQ_DA** (Energy-Charts has no public ID series; official reBAP was not fetchable). These figures are **not** a measured ID-index or official reBAP backtest.

| Policy | Net EUR | Δ vs locked DA | Δ€/day (90% CI) |
|---|---:|---:|---|
| Locked DA schedule (climatology P50) | 60,379 | — | — |
| Post-DA re-opt, full ID close | **83,394** | **+23,015** | **+63.23 [52.36, 73.28]** |
| Same, ASSUMED 20% unfilled at reBAP proxy | 83,408 | +23,029 | +63.27 [52.40, 73.32] |

The 20% unfilled case is **€14** higher only because it avoids ECC ID fees of 0.035 €/MWh on leftover volume; that is not an official reBAP effect. Design: [INTRADAY.md](INTRADAY.md).

## 7. Cost-aware CVaR frontier

Source: [`packages/forecast/results/CVAR_FRONTIER.md`](../packages/forecast/results/CVAR_FRONTIER.md), `packages/forecast/results/cvar_frontier.json`. Sourced fees, α = 5%, last 60 causal daily paths, window **8,736** h. Not a re-run of the 65,473 EUR ML path.

| λ | Net EUR | Mean €/day | OOS CVaR₅% loss € |
|---:|---:|---:|---:|
| 0 | 69,622 | 191.27 | 18.56 |
| 0.5 | 68,905 | 189.30 | 11.47 |
| 1 | 67,864 | 186.44 | 9.09 |
| 2 | 66,718 | 183.29 | 6.34 |
| 5 | 63,743 | 175.12 | 6.68 |
| 10 | 61,178 | 168.07 | 4.21 |

λ = 1–2 **improved** the trade-off. **λ = 5 did not** improve OOS CVaR versus λ = 2 (6.68 vs 6.34). Design: [CVAR.md](CVAR.md).

## 8. Near-live paper pilot

Source: [`results/live/LIVE_PILOT.md`](../results/live/LIVE_PILOT.md). Re-run **2026-11-10** (Asia/Karachi), sourced fee preset. Window **2026-10-28 → 2026-11-10** (14 days / 336 h). Latest published Energy-Charts DE-LU day in that run: **2026-11-10**. Paper trading only.

| Check | Result |
|---|---|
| Forecast MAE | ML+fund+CQR **39.20** vs naive **75.68** €/MWh |
| Forecast RMSE | ML **46.89** vs naive **84.12** €/MWh |
| P10–P90 coverage | **52.4%** (nominal 80%; short window) |
| ML gross / net cash | **3,816** / **3,351** € (capture **88.9%** / **87.0%** of PF) |
| Threshold gross / net | 1,261 / 1,051 € |
| PF gross / net | 4,293 / 3,852 € |
| Next delivery day | **2026-11-11** (DA not yet published as of that run): 4h charge / 4h discharge / 16h hold, P50 mean **351.48** €/MWh |

Coverage on this short, high-price window remains well below 80%.

## 9. Earlier short window (kept for continuity)

**2026-08-01 → 2026-10-15**, **1,824** h, price-only ML: threshold **9,993** € · climatology LP **14,145** € · ML **14,358** € · PF **25,228** € (ML **56.9%** of PF). That short sample understated the value of fundamentals. Package READMEs under `packages/core`, `packages/data`, `packages/risk`, and `packages/strategies` also report this window.

## 10. Simulator demo

Source: [`docs/SIMULATOR.md`](SIMULATOR.md). Synthetic `normal` scenario, seed 0, 168 h, paper only: ML net **150.37**, threshold **0**, PF oracle **546.42**. These are demo-path figures, not the 12-month backtest.

## Source files

| File | Role |
| --- | --- |
| `packages/forecast/results/long_window_eval.json` | 12-month forecast eval |
| `packages/forecast/results/costs_mondrian_equity.json` | Assumed-cost accounting-only table |
| `packages/forecast/results/cost_aware_tight_mondrian.json` | Cost-aware LP + tight Mondrian |
| `packages/forecast/results/sourced_fees_backtest.json` | Sourced-fee cost-aware re-run |
| `packages/forecast/results/GATE_CLOSURE_BIDDING.md` | Bid-curve backtest |
| `packages/forecast/results/INTRADAY_IMBALANCE.md` | ID / imbalance proxies |
| `packages/forecast/results/CVAR_FRONTIER.md` | CVaR frontier |
| `results/live/LIVE_PILOT.md` | Near-live paper pilot |
| `packages/backtest/figures/` | Equity and coverage plots |
