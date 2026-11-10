# Live paper pilot — 2026-10-28 → 2026-11-10

Run at (Asia/Karachi): **2026-11-10 08:02:39.101764+05:00**

Data: Energy-Charts DE-LU day-ahead + DE day-ahead load/solar/wind (CC BY 4.0).
Latest published DA price day: **2026-11-10**.
Fee toggle: **on** (cost-aware LP: True).

## Accuracy (ex-ante vs realised DA)

| Model | MAE €/MWh | RMSE €/MWh |
|---|---:|---:|
| ML + fundamentals + CQR | 39.20 | 46.89 |
| Naive day-ahead | 75.68 | 84.12 |

P10–P90 coverage: **52.4%** (nominal 80%), n=14 days.

## Paper P&L (1 MW / 2 MWh, day-locked ex-ante ML schedule)

| Strategy | Gross € | Net of ASSUMED costs € | Capture of PF (gross / net) |
|---|---:|---:|---|
| ML ex-ante LP (P50; net uses cost-aware LP when toggle on) | 3816.11 | 3301.20 | 88.9% / 86.7% |
| Threshold (causal) | 1260.84 | 1028.22 | — |
| Perfect foresight (oracle) | 4293.37 | 3806.17 | 100% |

Gross is mid-price P&L with no fee/slippage/degradation. Net uses ASSUMED fee 0.05, slippage 0.50, degradation 5 €/MWh. Previous pilots included core default degradation (5 €/MWh) but not fee/slippage.

## Tomorrow schedule (2026-11-11)

DA prices published: **no**. Forecast-only paper schedule. Mean P50 **351.48** €/MWh
(P10 326.16 / P90 376.81).
Charge hours: 4 · Discharge hours: 4 · Hold: 16 · start SoC 0.05.

## What this validates / does not

**Validates:** ex-ante DA forecast skill, interval coverage, paper capture of a forecast-based daily LP vs oracle on realised DA, gross vs net-of-ASSUMED-cost paper P&L.

**Does not validate:** real orders, SDAC bidding before gate closure, intraday/imbalance/ancillary.
