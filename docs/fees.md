# Market fees and paper-trading cost presets

**Retrieval date:** 2026-11-10 (Asia/Karachi).  
**Scope:** illustrative German **DE-LU** day-ahead paper battery (1 MW / 2 MWh).  
**Paper trading only** — this document does not describe exchange connectivity, membership onboarding, or real orders.

Every figure below is either copied from a public document opened on the retrieval date, or explicitly flagged as **not found**, **historical**, **assumed**, or **not applied**. Nothing is invented. Current EPEX SPOT €/MWh trading fees are **not** in the public Price List Guide.

Code: [`packages/backtest/src/gridpilot_backtest/fees.py`](../packages/backtest/src/gridpilot_backtest/fees.py) and the `sourced` / `assumed` (`base`) presets in [`costs.py`](../packages/backtest/src/gridpilot_backtest/costs.py).

## Presets used in the paper model

| Preset | Fee €/MWh | Slippage €/MWh | Degradation €/MWh throughput | What it is |
| --- | ---: | ---: | ---: | --- |
| `assumed` / `base` | 0.05 | 0.50 | 5.0 | Previous defaults (A-C1–A-C3). All three legs are **ASSUMED**. |
| **`sourced`** | **0.015** | **0.00** | **5.0** | ECC Lux day-ahead **clearing** only + auction-fill slippage 0. Degradation is **still ASSUMED**. |
| `zero` | 0 | 0 | 0 | Gross mid-price accounting. |

The sourced **fee** is a **lower bound** on total exchange costs: the current EPEX SPOT trading fee is not printed in the public 2026 Fees page or Price List Guide, so it is **omitted** rather than guessed. Annual membership / technical fees are disclosed below and are **not** amortised into the per-MWh number (that would be a modelling choice, not a published tariff). Intraday ECC clearing (0.035 €/MWh) is documented but **not** added, because this paper model is day-ahead only.

## Sourced vs still-assumed vs not found

| Item | Status | Figure | Tariff year | Source (retrieved 2026-11-10) |
| --- | --- | --- | --- | --- |
| EPEX SPOT DA trading fee (DE-LU) | **Not found** in current public docs | — | 2026 | [EPEX Fees](https://www.epexspot.com/en/fees) and [Price List Guide (PDF)](https://www.epexspot.com/sites/default/files/download_center_files/New%20Price%20List%20Guide.pdf) — packages described qualitatively; contact sales@epexspot.com |
| EPEX SPOT DA trading fee (historical) | Historical, **not used** | 0.04 €/MWh DE-AT-CH DA; 0.10 ID | 2015 | [2015 price list](https://abcdocz.com/doc/668004/price-list---epex-spot) on an unofficial host; stale |
| ECC Lux DA spot clearing | **Sourced** | **0.015 €/MWh** | 2026 | [ECC Price List 085b, 2 Nov 2026](https://www.ecc.de/fileadmin/ECC/Downloads/About_ECC_AG/Rules/Price_List/Current_Price_List/20261102_ECC_Price_List_085b.pdf) §4.1; index at [ECC Rules](https://www.ecc.de/en/rules-regulations/rules) |
| ECC Lux intraday / SIDC IDA clearing | **Sourced** (not in DA preset) | 0.035 €/MWh | 2026 | Same ECC 085b §4.1 (footnote: also IDAs) |
| ECC membership (fixed) | **Sourced** (not in per-MWh preset) | NCM 1,000 €/year; Institution CM 12,500 €/year; DCP Power Markets Plus 12,500 €/year; EUREX GUI 7,500 €/year (not DCP) | 2026 | Same ECC 085b §2–3. NCM fee is credited against clearing fees; first 12 months waived for NCM/ICM |
| Nord Pool DA trading + clearing | **Sourced comparator** (not in preset) | 0.040 + 0.015 = **0.055 €/MWh** | 2026 | [Nord Pool Fee Schedule, Nordic/Baltic, effective 1 Jan 2026](https://www.nordpoolgroup.com/4a7ad8/globalassets/trading-and-services/nord-pool-fee-schedule-2026-nordic-and-baltic-market.pdf). Participant access DA+ID 21,500 €/year. Note (b) lists Germany/Luxembourg among areas for the 65,000 € access-fee cap. The PDF title is Nordic/Baltic; a separate public CWE/DE-LU schedule was **not found**. **Not** used as a stand-in for EPEX DE-LU |
| DA slippage / bid-ask | **Sourced** (market design) | **0 €/MWh** | 2026 | SDAC day-ahead is a **single clearing price** per MTU. The 0.50 €/MWh assumed preset is a modelling conservatism (A-C2), not a published fee |
| Grid-access charges on stored energy (Netzentgelte) | **Sourced** (statutory, conditional) | **0 €/MWh** if eligible | 2026 | [EnWG § 118(6)](https://www.gesetze-im-internet.de/enwg_2005/__118.html): storage commissioned after 31 Dec 2008 and from 4 Aug 2011 within 18 years (by 4 Aug 2029), 20-year exemption from *Entgelte für den Netzzugang* on energy withdrawn for storage and fed back into the **same** grid. Does not automatically cover all levies/concession fees |
| Imbalance (reBAP) | **Not applied** | Quarter-hourly published price, not a fixed tariff | 2026 | [Netztransparenz — Ausgleichsenergiepreis](https://www.netztransparenz.de/de-de/Regelenergie/Ausgleichsenergiepreis). The DA-only paper model settles planned volumes at the DA price, so no imbalance volume is simulated |
| Battery degradation | **Assumed** | **5 €/MWh** throughput | — | No public €/MWh wear tariff. [NREL/NLR ATB 2025 utility-scale battery storage](https://atb.nlr.gov/electricity/2025/utility-scale_battery_storage) gives 15-year life, ~1 cycle/day, VOM = 0, FOM = 4% of CAPEX including augmentation. A primary 2024 overnight $/kWh table was not retrieved this day (NREL PDF TLS failure), so **no €/MWh is derived**. A-C3 / Kies et al. 2018 ([DOI 10.1088/1742-6596/977/1/012005](https://doi.org/10.1088/1742-6596/977/1/012005)) is order-of-magnitude framing only |

## What a buyer should not conclude

- These are **paper-trading** cost assumptions for a public research agent, not a quote from EPEX, ECC, a TSO, or a broker.
- The sourced variable fee (**0.015 €/MWh**) is **ECC clearing only**. Real all-in exchange costs may be higher once a current EPEX trading fee and annual membership are included.
- Nord Pool’s 0.055 €/MWh DA combined fee is a **published NEMO comparator**, not evidence of the current EPEX DE-LU trading rate.
- Grid exemption is **conditional** (commissioning window, same-grid). It is not a blanket zero for every levy.
- **No real-money performance** is claimed. Day-ahead only; no exchange connectivity; imbalance not simulated.

## How the paper code uses this

```text
from gridpilot_backtest.costs import get_cost_preset
costs = get_cost_preset("sourced")   # or "assumed"
```

- 12-month cost-aware backtest: `python packages/forecast/scripts/run_cost_aware_tight_mondrian.py --costs sourced --skip-forecast`
- Near-live paper pilot: `python packages/live/scripts/run_live_pilot.py --costs sourced`

## Measured paper results (sourced preset, 2026-11-10)

Same window as the assumed-cost cost-aware run: **2025-11-01 → 2026-10-30**, 8,735 h, DE-LU day-ahead (Energy-Charts / SMARD, CC BY 4.0). Paper trading only. Cost-aware LP was **re-optimised** under the sourced preset; accounting-only baselines were repriced from earlier dumps. Forecast skill is unchanged (costs do not enter the forecast).

| Strategy | Net cash € | Capture of cost-aware PF | Δ€/day vs threshold (90% CI) |
| --- | ---: | ---: | --- |
| Threshold | 32,367 | 39.3% | — |
| ML, accounting-only | 58,277 | 70.8% | +71.2 [55.3, 84.0] |
| **ML cost-aware LP** | **65,473** | **79.6%** | **+90.9 [76.6, 104.7]** |
| ML cost-aware + tight Mondrian | 65,312 | 79.4% | +90.5 [76.5, 104.6] |
| **Cost-aware PF** | **82,271** | **100%** | +137.1 [119.0, 152.7] |

Under the earlier **assumed** preset (0.05 / 0.50 / 5) the same cost-aware ML printed **64,646** € (79.5% of 81,314). Sourced net is slightly higher mainly because the variable fee is lower and DA slippage is 0; degradation (still ASSUMED 5 €/MWh) remains the dominant cost line (cost-aware ML: **€8,219** degradation vs **€25** fees). Near-live 14-day paper pilot (2026-10-28 → 2026-11-10): ML gross / net **3,816 / 3,351** € (88.9% / 87.0% of PF). These are not real-money results.
