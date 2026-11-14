# Gate-closure bid curves vs locked schedule (paper only)

Window: 2025-11-01 → 2026-10-30  (364 days, 8736 hours).
Gate closure: 12:00 Europe/Berlin on D-1. First deadline: 2025-10-31 12:00:00+01:00.
Forecast: **climatology** — Causal 90-day hour-of-day climatology (P10/P50/P90); same fan for all policies.
Costs: sourced preset (see `docs/fees.md`); marginal price-tie fraction ASSUMED 0.5.

Water values are the opportunity cost of stored energy from a remaining-day cost-aware LP on the P50 path (finite difference of paper cash vs starting SoC). There is no terminal value for leftover end-of-day SoC — the same convention as the locked daily LP. Bid limits are centred on the resulting reservation prices; P50−P10 / P90−P50 still set the fan width. Paper trading only.

## Final net cash (EUR)

| Policy | Net EUR | Throughput MWh | Cycles |
| --- | ---: | ---: | ---: |
| Locked P50 cost-aware schedule | 60379.21 | 1831.2 | 457.8 |
| Quantile bid curves (P10/P50/P90) | 13081.61 | 602.6 | 150.7 |
| Schedule-anchored bid curves | 17739.57 | 301.6 | 75.4 |
| Water-value bid curves | 30675.43 | 848.1 | 212.0 |

- Quantile bids vs schedule: -47297.60 EUR — **did not improve** on this window.
- Anchored bids vs schedule: -42639.63 EUR — **did not improve** on this window.
- Water-value bids vs schedule: -29703.77 EUR — **did not improve** on this window.
- Water-value bids vs myopic quantile bids: +17593.83 EUR — **improved** on this window.

## Incremental daily value (moving-block bootstrap)

- Quantile bids − schedule: -129.94 €/day  90% CI [-149.98, -107.28]  (n=364, block=7d, boot=400)
- Anchored bids − schedule: -117.14 €/day  90% CI [-139.04, -94.56]  (n=364, block=7d, boot=400)
- Water-value bids − schedule: -81.60 €/day  90% CI [-99.12, -61.52]  (n=364, block=7d, boot=400)
- Water-value bids − quantile bids: 48.33 €/day  90% CI [39.45, 58.87]  (n=364, block=7d, boot=400)

A CI that contains 0 means the year-long difference is not distinguishable from noise at 90% under weekly blocks.

## What this does and does not show

- Same forecast fan for every policy; no lookahead into delivery-day prices.
- The locked schedule is a price-taking fill of the cost-aware LP on P50 (the current approach).
- Myopic quantile curves bid around each hour's own P10/P50/P90 and have no water value, so they under-cycle relative to the locked schedule.
- Water-value curves buy only below ``η_c · wv − add`` and sell only above ``wv / η_d + add``. They can still miss a fill when the realised price is inside the reservation but the P50 path (and therefore wv) was wrong.
- Intra-day water value only: leftover SoC at the end of the delivery day is worthless in the LP, so a late-day reservation can be lower than a multi-day storage valuation would suggest.
- Climatology is not the production ML+CQR fan. Figures are not comparable to the published ML cost-aware 65,473 EUR path without a `--forecast ml` run.
- Paper trading only; no real orders.
