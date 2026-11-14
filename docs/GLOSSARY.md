# Glossary

Short definitions as they are used in this repository. See [METHODOLOGY.md](METHODOLOGY.md) for the maths.

| Term | Meaning here |
| --- | --- |
| **BESS** | Battery energy storage system. The published paper runs use an illustrative **1 MW / 2 MWh** unit. |
| **SoC** | State of charge. Band **5–95%** (ASSUMED) in the published configs. |
| **η (eta)** | One-way charge / discharge efficiency. Published default **0.95 / 0.95** (ASSUMED). |
| **Cycle / throughput** | A full cycle is treated as 2 MWh of one-way throughput on the 2 MWh unit (charge plus discharge energy, as implemented in the battery model). A **2 cycles/day** cap is applied in `PaperAgent` / simulator risk limits. |
| **DE-LU** | The German–Luxembourg bidding zone for the day-ahead auction. |
| **DA** | Day-ahead. Here, the SDAC auction that sets a single clearing price per MTU for delivery day D. |
| **ID** | Intraday. Continuous or auction trading after DA publication. Energy-Charts has **no public ID series** in the checks documented on 2026-11-10. |
| **SIDC / IDA** | Single Intraday Coupling / intraday auctions. ECC lists a separate ID clearing fee (0.035 €/MWh) that is documented in [fees.md](fees.md) and used only in the ID layer, not in the DA sourced preset. |
| **SDAC** | Single Day-Ahead Coupling, the pan-European day-ahead auction. Gate closure in this repo is **12:00 Europe/Berlin on D-1**. Publication is treated as ~12:45; the simulator’s first post-publication hourly tick is **13:00** on D-1. |
| **MTU** | Market time unit. Energy-Charts often delivers 15-minute prices; this repo averages them to hourly means unless a script says otherwise. |
| **P10 / P50 / P90** | Forecast quantiles: 10th, 50th (median), and 90th percentiles of the next-day price. The P10–P90 band is a nominal **80%** interval. In `packages/core`, daily PnL **P10/P50/P90** are empirical percentiles of realised paper cash, not the price forecast. |
| **CQR** | Conformalized quantile regression. Adjusts a raw quantile band using past residuals, with a delay so that calibration is available at gate closure. |
| **Mondrian CQR** | CQR split by regime (hour, residual-load tercile, volatility in the tight variant) with separate lower/upper tails and a parent-regime fallback when a cell is thin. |
| **LEAR** | Lago et al. style autoregressive day-ahead model. **LEAR-lite** here is 24 hourly LassoLarsIC regressions on asinh-scaled price lags and calendar features, plus optional day-ahead fundamentals. |
| **CVaR** | Conditional Value at Risk (Expected Shortfall). In the CVaR LP, \(\alpha = 0.05\) is the **tail probability** (worst 5%), not a 95% “confidence” label. Out-of-sample CVaR₅% in result tables is the historical CVaR of daily paper cash. |
| **VaR** | Value at Risk. Historical quantile of the loss distribution; used in `packages/risk`. Distinct from CVaR, which averages the tail beyond VaR. |
| **Rockafellar–Uryasev** | Representation \(\mathrm{CVaR}_\alpha(L)=\min_\zeta\{\zeta+(1/\alpha)\mathbb{E}[(L-\zeta)_+]\}\). See [METHODOLOGY.md](METHODOLOGY.md). |
| **Cost-aware LP** | Daily dispatch LP that puts fee + slippage + degradation into the **objective**, not only into after-the-fact accounting. |
| **Accounting-only** | A cost-blind schedule whose fills are later charged the cost preset. A different policy from the cost-aware LP. |
| **Perfect foresight (PF)** | An **oracle** that sees realised DA prices when planning. It is a ceiling, not a tradeable strategy. |
| **Capture** | A strategy’s net paper cash divided by the relevant perfect-foresight cash (accounting-only or cost-aware, as labelled). |
| **Threshold strategy** | `ThresholdArbitrage`: charge and discharge around fixed price thresholds. The simple baseline in most tables. |
| **Gate-closure bid curve** | A stepwise buy/sell price-quantity curve submitted at SDAC gate, built from P10/P50/P90, then cleared against the realised price. |
| **Locked schedule** | Price-taking cost-aware LP on the same P50 fan, used as the bid-curve baseline. |
| **Water value** | Opportunity cost of stored energy (€/MWh): a finite difference of subsequent-hour cost-aware LP cash on the P50 path. Bid limits centre on `η_c · wv − add` / `wv / η_d + add`. Intra-day only; leftover end-of-day SoC has no terminal value. |
| **reBAP** | *regelzonenübergreifender einheitlicher Bilanzausgleichsenergiepreis*, the German imbalance settlement price. Official series require Netztransparenz OAuth and were **not fetchable** for the published runs. |
| **PROXY_ID_EQ_DA / PROXY_REBAP_EQ_DA** | Labelled stand-ins that set the ID mid (or reBAP) equal to the realised DA price. They measure post-DA reshaping with **no ID–DA spread**. They are not official ID-index or reBAP data. |
| **Block bootstrap** | Resampling of daily cash differences in moving 7-day blocks (400 draws, 90% percentile CI) to respect weekly dependence. |
| **Paper trading** | Simulated fills and cash. **No** exchange connectivity and **no** real orders. Figures are not real-money performance. |
| **Energy-Charts / SMARD** | Public DE-LU prices and TSO day-ahead load/solar/wind forecasts, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), Bundesnetzagentur / Fraunhofer ISE. Always attribute. |
| **ECC** | European Commodity Clearing. The sourced DA fee **0.015 €/MWh** is ECC Lux day-ahead **clearing** only (Price List 085b, 2 Nov 2026). |
| **EPEX SPOT** | Power exchange for DE-LU DA. The current public trading fee was **not found** on the 2026 Fees page / Price List Guide and is omitted from the sourced preset. |
| **EnWG § 118(6)** | Conditional German grid-charge exemption for eligible storage. Modelled as **0 €/MWh** grid fee *if eligible*; not a blanket zero for every levy. |
| **ASSUMED** | A modelling default that is not copied from a current public tariff. Degradation **5 €/MWh** is the main example. |
