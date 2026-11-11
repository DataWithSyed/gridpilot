# Methodology

This page describes the paper-trading methods used in the published GridPilot runs. It does not introduce new numbers; results live in [RESULTS.md](RESULTS.md). **Paper trading only.**

## Asset and market

The illustrative battery is **1 MW / 2 MWh**, one-way efficiencies **η = 0.95 / 0.95** (ASSUMED), SoC band **5–95%** (ASSUMED), and a **2 cycles/day** cap in the `PaperAgent` / simulator risk limits. The market is the DE-LU day-ahead auction. Energy-Charts 15-minute MTUs are averaged to hourly means unless a script says otherwise. Prices and day-ahead load/solar/wind forecasts are [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) from Energy-Charts / SMARD (Bundesnetzagentur).

## SDAC gate timing and no lookahead

Day-ahead bids or schedules for delivery day **D** are treated as submitted at **12:00 Europe/Berlin on D-1**, the SDAC gate-closure time used in this repo (`gate_closure_time` in `gridpilot_forecast.bid_curves`, `is_gate_closure_tick` in the simulator clock).

The forecast for D uses only prices and fundamentals with delivery time **strictly before D**. By 12:00 on D-1, day D-1 prices have already been published (around 12:45 on D-2). Realised prices for D are used only at settlement. The simulator additionally treats **13:00 Europe/Berlin on D-1** as the first hourly tick after DA publication (~12:45), when a post-DA re-optimisation may run.

Perfect-foresight strategies are labelled oracles and are never used as inputs to a tradeable policy.

## Forecast features and models

`WalkForwardQuantileForecast` is the production-style forecaster in the 12-month runs:

- Quantiles **P10 / P50 / P90**.
- Lookback **90** days, refit every **7** days (both ASSUMED in the published scripts).
- Models: Lago-style naive (D-1, or D-7 on Mon/Sat/Sun), **LEAR-lite** (24 hourly LassoLarsIC on asinh-scaled price lags and calendar features), **quantile GBM** (`HistGradientBoostingRegressor` with quantile loss), and an equal-weight **ensemble** (ASSUMED weights).
- Optional **day-ahead fundamentals**: TSO forecasts of load, solar, and wind from Energy-Charts `public_power_forecast`, combined into residual-load features for delivery day D. Same-day realised prices do not enter features.

Some later same-fan bidding and CVaR experiments are **price-only** (no fundamentals panel) or use a causal hour-of-day climatology. Those runs are labelled in [RESULTS.md](RESULTS.md) and are not substitutes for the published fundamentals + ML path.

## Rolling CQR and Mondrian CQR

Conformalized quantile regression adjusts the raw P10–P90 band using past residuals only, with a delay so that the calibration set is available at gate closure. `RollingCQR` is a single global window (published window **60** days, delay **2**, nominal 80% band, α = 0.20).

`MondrianAsymmetricCQR` splits residuals by regime and calibrates lower and upper tails separately. The **tight** Mondrian used in later runs labels hour-of-day × hourly residual-load tercile × 7-versus-60-day hour-of-day volatility, with parent-regime fallback when a cell is thin. Coverage is reported against a nominal **80%** P10–P90 interval. In the published 12-month window, even tight Mondrian (**78.9%**) remains slightly short of 80%.

Calibration quality is not assumed to raise trading profit; several runs show the opposite (see Results).

## Cost-aware dispatch LP

`solve_day_lp_with_costs` chooses a here-and-now daily schedule on a price path (usually the P50 forecast, or realised prices for the oracle). Execution costs enter the **objective**, not only the accounting after the fact. With addend \(a = f + s + d\) (fee + slippage + degradation, €/MWh):

$$
\min_{g^{\mathrm{in}},\,g^{\mathrm{out}}}
\sum_t \Big[
  g^{\mathrm{in}}_t \,(\pi_t + a)
  + g^{\mathrm{out}}_t \,(-\pi_t + a)
\Big]
$$

subject to power limits \(0 \le g^{\mathrm{in}}_t, g^{\mathrm{out}}_t \le P\,\Delta t\), and SoC dynamics

$$
E_t = E_{t-1} + \eta_c \, g^{\mathrm{in}}_t - g^{\mathrm{out}}_t / \eta_d,
\qquad
E_{\min} \le E_t \le E_{\max}.
$$

`BatteryConfig.degradation` is not added a second time when `ExecutionCosts.degradation_eur_per_mwh` is already in \(a\). The default published preset is **sourced**: fee **0.015** €/MWh (ECC DA clearing), slippage **0** (SDAC single clearing price), degradation still **ASSUMED 5** €/MWh. See [fees.md](fees.md).

An earlier **accounting-only** layer applies the same costs to fills after a cost-blind schedule. Re-optimising the LP for costs is a different policy and is reported separately.

## CVaR LP (Rockafellar–Uryasev)

`solve_day_lp_cvar` keeps a single here-and-now schedule against a set of causal price scenarios (in the published frontier: the last **60** completed Berlin days, hour-aligned). Let \(\mathrm{cash}_s\) be the cost-aware cash of that schedule under scenario \(s\), and \(\mathrm{loss}_s = -\mathrm{cash}_s\). The programme maximises expected cash minus a penalty on tail loss:

$$
\max \; \mathbb{E}[\mathrm{cash}] - \lambda \,\mathrm{CVaR}_{\alpha}(\mathrm{loss})
$$

with tail probability \(\alpha = 0.05\) (worst 5%) and the Rockafellar–Uryasev representation

$$
\mathrm{CVaR}_{\alpha}(L)
= \min_{\zeta}
\left\{
  \zeta + \frac{1}{\alpha}\,\mathbb{E}\big[(L - \zeta)_+\big]
\right\}.
$$

The published frontier sweeps \(\lambda \in \{0, 0.5, 1, 2, 5, 10\}\) under the sourced fee preset. Out-of-sample CVaR is the historical CVaR₅% of realised daily paper cash, not the in-sample LP value. Higher \(\lambda\) is not guaranteed to improve *out-of-sample* CVaR (λ = 5 did not beat λ = 2 on that window).

## Gate-closure bid curves

At 12:00 Europe/Berlin on D-1, P10/P50/P90 are turned into a default three-step buy/sell price-quantity curve. Buy limits run from \(p_{50} - a\) down to \(p_{10} - a\); sell limits from \(p_{50} + a\) up to \(p_{90} + a\). A buy (sell) step is accepted when the realised clearing price is at or below (at or above) the limit. When a limit **equals** the clearing price, **50%** of that step is accepted — an **ASSUMED** tie-break, because the official SDAC residual merit-order is not available. SoC and power clipping is a second, physical partial-acceptance step. The locked cost-aware P50 schedule on the **same** fan is the price-taking baseline. Details: [BIDDING.md](BIDDING.md).

## Post-DA re-optimisation and imbalance

After DA prices are published, the delivery day can be re-solved and the delta booked as an intraday trade. Energy-Charts has **no public ID or ID-index series** (checked 2026-11-10). Official reBAP requires Netztransparenz OAuth and was **not fetchable**. The published layer therefore uses labelled proxies **PROXY_ID_EQ_DA** and **PROXY_REBAP_EQ_DA** (both legs equal the realised DA price). That measures the value of reshaping after DA publication assuming ID trades occur at DA, with **no ID–DA spread**. It is not a measured ID-index or official reBAP backtest. Details: [INTRADAY.md](INTRADAY.md).

## Block-bootstrap confidence intervals

`block_bootstrap_mean_diff_ci` in `gridpilot_backtest.metrics` compares two daily cash series. It forms the intersection of dates, takes the daily difference, and resamples with a **moving block of 7 days** (ASSUMED weekly dependence), **400** bootstrap draws, and a **90%** percentile interval on the mean difference (α = 0.10). A CI that contains 0 means the year-long mean gap is not distinguishable from noise at that level under weekly blocks.

## What is not modelled

No real orders, no official ID-index or reBAP series in the published runs, no EPEX trading fee (not in the public 2026 price list), no amortised ECC membership in the per-MWh preset, and degradation remains an assumption rather than a published €/MWh tariff.
