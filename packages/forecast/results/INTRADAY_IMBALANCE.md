# Post-DA re-optimisation and imbalance (paper only)

Window: 2025-11-01 → 2026-10-30 (364 days, 8736 hours).
DA lock: causal 90-day hour-of-day P50 + cost-aware LP, sourced DA fees.
ID prices: **proxy_id_eq_da**. Energy-Charts public API has no intraday or ID-index series (verified 2026-11-10: only /price day-ahead; market=intraday is ignored). ID mid is proxied by the realised DA clearing price.
reBAP: **proxy_rebap_eq_da**. Netztransparenz reBAP API requires Extranet OAuth client credentials (docs v1.14, 2025-02-07); unauthenticated data URLs returned 404. Imbalance is cashed out at the realised DA price unless a local series is provided.
Partial-close unfilled fraction: ASSUMED 20%. ECC ID clearing 0.035 €/MWh on filled ID volume.

## Final net cash (EUR)

| Policy | Net EUR | ID throughput MWh | |imbalance| MWh |
| --- | ---: | ---: | ---: |
| Locked DA schedule (no ID) | 60379.21 | — | — |
| Post-DA re-opt, full ID close (unfilled 0) | 83393.79 | 2024.2 | 0.0 |
| Post-DA re-opt, ASSUMED 20% unfilled at reBAP proxy | 83407.96 | 1619.3 | 404.8 |

- Full ID close vs locked DA: +23014.58 EUR — **improved**.
- 20% unfilled vs locked DA: +23028.75 EUR — **improved**.

## Incremental daily value (moving-block bootstrap, 7 d, 400 draws, 90% CI)

- Full ID close − locked DA: 63.23 €/day  90% CI [52.36, 73.28] (n=364)
- 20% unfilled − locked DA: 63.27 €/day  90% CI [52.40, 73.32] (n=364)

## What this does and does not show

- This is **not** a real ID-index or official reBAP backtest. Both legs are proxied by realised DA because those series were not publicly fetchable.
- Under PROXY_ID_EQ_DA, the lift is the value of reshaping after DA prices are published, minus ECC ID fees, with no ID–DA spread.
- PROXY_REBAP_EQ_DA ignores scarcity adders; the 20% unfilled case is an ASSUMED residual, not a measured fill rate.
- Paper trading only; no real orders.
