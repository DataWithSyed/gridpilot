# Gate-closure bid curves vs locked schedule (paper only)

Window: **2025-11-01 → 2026-10-30** (364 days, **8,736** hours; spring/fall DST cancel).
Gate closure: **12:00 Europe/Berlin on D-1**. First deadline: 2025-10-31 12:00 Europe/Berlin.
Costs: **sourced** preset (ECC DA clearing 0.015 €/MWh, DA slippage 0, degradation still ASSUMED 5 €/MWh). See `docs/fees.md`.
Battery: 1 MW / 2 MWh, η 0.95/0.95, SoC 5–95%. Paper trading only — no real orders.
Marginal price-tie fraction ASSUMED 0.5 (no SDAC residual merit-order is available).

Both policies on a given row see the **same** P10/P50/P90 fan. The locked schedule is a price-taking fill of the cost-aware LP on P50 (day-locked at gate closure). Quantile bid curves convert the fan into 3-step buy/sell price-quantity curves and clear against the realised price with SoC partial acceptance. Schedule-anchored curves centre volume on the LP plan and add P10/P90 tails.

These schedule cash figures are **not** a replacement for the published sourced cost-aware ML path (**65,473** EUR, 411 cycles). That published run used fundamentals, PaperAgent cycle/drawdown clips, and the live cost-aware agent path. The ML fan here is **price-only** (no fundamentals), day-locked (no hourly re-optimisation), and unclipped by the 2-cycle/day risk limit (ML schedule **479.4** cycles). Compare **bid vs schedule on the same fan only**.

## 12-month results

| Forecast | Policy | Net EUR | Throughput MWh | Cycles |
| --- | --- | ---: | ---: | ---: |
| Causal 90-day hour-of-day climatology | Locked P50 cost-aware schedule | 60,379.21 | 1,831.2 | 457.8 |
| Causal 90-day hour-of-day climatology | Quantile bid curves (P10/P50/P90) | 13,081.61 | 602.6 | 150.7 |
| Causal 90-day hour-of-day climatology | Schedule-anchored bid curves | 17,739.57 | 301.6 | 75.4 |
| Walk-forward ML + tight Mondrian (price-only) | Locked P50 cost-aware schedule | 75,101.52 | 1,917.5 | 479.4 |
| Walk-forward ML + tight Mondrian (price-only) | Quantile bid curves (P10/P50/P90) | 3,566.38 | 751.6 | 187.9 |
| Walk-forward ML + tight Mondrian (price-only) | Schedule-anchored bid curves | 22,866.78 | 389.7 | 97.4 |

## Incremental daily value (moving-block bootstrap, block=7 d, 400 draws, 90% CI)

| Forecast | Contrast | Mean €/day | 90% CI |
| --- | --- | ---: | --- |
| Climatology | Quantile bids − schedule | −129.94 | [−149.98, −107.28] |
| Climatology | Anchored bids − schedule | −117.14 | [−139.04, −94.56] |
| ML price-only | Quantile bids − schedule | −196.53 | [−222.03, −171.41] |
| ML price-only | Anchored bids − schedule | −143.50 | [−163.33, −122.56] |

Every CI **excludes 0**. Standalone quantile curves and schedule-anchored curves **did not improve** on the locked cost-aware schedule on this window.

A 30-day ML confirmation on **2026-10-01 → 2026-10-30** (721 h) showed the same sign: schedule 7,812.86 vs quantile bids 31.55 vs anchored 2,174.67 EUR; quantile − schedule **−259.38 €/day**, 90% CI [−309.23, −178.10].

## What helped, and what did not

- **Did not help:** turning P10/P50/P90 into myopic hourly bid curves. The curves under-cycle (150–188 cycles vs 458–479 for the locked schedule) because they have no explicit water value or intra-day SoC plan. They correctly refuse some forecast misses, but they also skip profitable planned cycles when the realised price sits between the steps or the battery is in the wrong state from earlier refusals. Anchored curves are better than standalone quantile curves under ML (22,867 vs 3,566) but still far behind the locked schedule (75,102).
- **Did help as infrastructure:** the gate-closure curve builder, SDAC-style clearing with partial acceptance, and a fair same-fan backtest are in place for later work (water-value bids, intraday re-optimisation, imbalance). Tests cover causality, SoC clipping, ties, negative prices, and a toy case where bids correctly skip an unprofitable locked charge.
- Climatology and ML fans agree on the **direction** of the result.

## How to reproduce

```bash
python packages/forecast/scripts/run_gate_closure_bidding.py --forecast climatology --costs sourced
python packages/forecast/scripts/run_gate_closure_bidding.py --forecast ml --costs sourced
```

Paper trading only. Machine-readable numbers: `packages/forecast/results/gate_closure_bidding.json`. Design notes: `docs/BIDDING.md`.
