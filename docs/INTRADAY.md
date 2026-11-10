# Intraday re-optimisation and imbalance (paper trading only)

This layer sits on top of a locked day-ahead schedule. After DA prices
are published (~12:45 Europe/Berlin on D-1) the remaining delivery day
is re-solved and deviations are booked as intraday trades and, if
unfilled, as imbalance. It never places real orders.

## Data availability (checked 2026-11-10 Asia/Karachi)

**Energy-Charts does not publish public intraday or ID-index prices.**
The documented API price endpoints are day-ahead only (`/price`,
`/v2/price`, `/v2/price_current`, `/v2/price_next_day`). A
`?market=intraday` query returns HTTP 200 but the values are
**identical** to the day-ahead series — the parameter is ignored.
There is no `/intraday_price` (404).

**Official reBAP was not fetchable.** Netztransparenz publishes
quarter-hourly Ausgleichsenergiepreise, but the data API (WebAPI docs
v1.14, 7 Feb 2025) requires OAuth 2.0 **client credentials issued in
the Netztransparenz Extranet**. Health-check
`https://ds.netztransparenz.de/api/v1/health` returns OK;
unauthenticated calls to
`/api/v1/data/NrvSaldo/reBAP/Qualitaetsgesichert` return 404. The
public HTML page is a chart UI with no bulk CSV in the document.

## Labelled proxies

| Series | Source used in the published run | Meaning |
| --- | --- | --- |
| ID mid | **PROXY_ID_EQ_DA** | ID price = realised DA clearing price. Measures the value of reshaping after DA publication, with **no ID–DA spread**. True ID value can be higher or lower. |
| reBAP | **PROXY_REBAP_EQ_DA** | Imbalance cashed out at realised DA. Ignores AEP scarcity adders. Not official reBAP. |

ECC ID clearing **0.035 €/MWh** (Price List 085b) is applied to filled
ID volume. EPEX ID trading fees remain unpublished and are omitted
(lower bound). Degradation is charged once on physical throughput.

An ASSUMED `unfilled_frac` (0 and 0.20 in the published run) leaves
that share of the intended ID volume as imbalance instead of an ID
fill. Under PROXY_REBAP_EQ_DA this does **not** introduce a distinct
imbalance price — it only avoids ID fees on the unfilled MWh — so it
is not a real reBAP stress test.

## Mechanics

1. Lock a cost-aware LP on the causal P50 fan at gate closure (same DA
   baseline as the bidding study).
2. After DA prices are known, re-solve the day on the ID proxy path
   (here: realised DA) with ID fees in the objective.
3. Physical dispatch follows the re-optimised plan. ID volume is the
   walk from the DA nomination to that plan. Leftover volume, if any,
   is imbalance: net extra export receives reBAP, net extra import
   pays reBAP.

## Results

See [`packages/forecast/results/INTRADAY_IMBALANCE.md`](../packages/forecast/results/INTRADAY_IMBALANCE.md).

On 2025-11-01 → 2026-10-30, under these proxies, full ID close
**improved** on the locked climatology DA schedule by **+23,015 EUR**
(**+63.23 €/day**, 90% CI **[52.36, 73.28]**). That lift is the value
of seeing the DA price and reshaping, minus ECC ID fees — not a
measured ID-spread profit and not official reBAP.

Reproduce:

```bash
python packages/forecast/scripts/run_intraday_imbalance.py --costs sourced
```

Paper trading only.
