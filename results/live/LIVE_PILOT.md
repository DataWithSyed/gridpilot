# Live paper pilot — 2026-10-28 → 2026-11-10

Run at (Asia/Karachi): **2026-11-10 03:42:24.827838+05:00**

Data: Energy-Charts DE-LU day-ahead + DE day-ahead load/solar/wind (CC BY 4.0).
Latest published DA price day: **2026-11-10**.

## Accuracy (ex-ante vs realised DA)

| Model | MAE €/MWh | RMSE €/MWh |
|---|---:|---:|
| ML + fundamentals + CQR | 39.20 | 46.89 |
| Naive day-ahead | 75.68 | 84.12 |

P10–P90 coverage: **52.4%** (nominal 80%), n=14 days.

## Paper P&L (1 MW / 2 MWh, day-locked ex-ante ML schedule)

| Strategy | Cash € | Capture of PF |
|---|---:|---:|
| ML ex-ante LP (P50 forecast) | 3352.23 | 87.0% |
| Threshold (causal) | 1051.27 | — |
| Perfect foresight (oracle) | 3853.23 | 100% |

## Tomorrow schedule (2026-11-11)

DA prices published: **no**. Forecast-only paper schedule. Mean P50 **351.48** €/MWh
(P10 326.16 / P90 376.81).
Charge hours: 4 · Discharge hours: 4 · Hold: 16 · start SoC 0.05.

## What this validates / does not

**Validates:** ex-ante DA forecast skill, interval coverage, paper capture of a forecast-based daily LP vs oracle on realised DA.

**Does not validate:** real orders, SDAC bidding before gate closure, intraday/imbalance/ancillary, fees/slippage.
