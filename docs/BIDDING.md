# Day-ahead gate-closure bidding (paper trading only)

GridPilot can now turn a P10/P50/P90 day-ahead fan into an SDAC-style
price-quantity curve and clear it against the realised DE-LU clearing
price. This is a **paper** model of gate-closure bidding. It never
places real orders and does not talk to an exchange.

## When curves are locked

Day-ahead bids for delivery day **D** are treated as submitted at
**12:00 Europe/Berlin on D-1**. The forecast for D uses only prices
with delivery time strictly before D (information that is already
published by that deadline: D-1 prices were released around 12:45 on
D-2). There is no lookahead into D's realised prices.

`gate_closure_time()` in `gridpilot_forecast.bid_curves` returns that
deadline.

## Curve construction

For each hour, a default **3-step** curve is built from the fan and
the cycle addend `add = fee + slippage + degradation` (€/MWh) of the
active cost preset (sourced by default):

- **Buy (charge)** limits run from `p50 - add` (most aggressive) down
  to `p10 - add`. A buy step is accepted when the clearing price is
  **at or below** the limit.
- **Sell (discharge)** limits run from `p50 + add` up to `p90 + add`.
  A sell step is accepted when the clearing price is **at or above**
  the limit.
- Curves are uncrossed: the highest buy limit stays strictly below
  the lowest sell limit (a `0.01` €/MWh gap if `add` is zero).
- Equal limits are merged.

A second **schedule-anchored** family centres the planned MW from the
cost-aware P50 LP as a mid step and offers leftover capacity only in
the P10 / P90 tails, so a hold hour can still react to extremes.

## Clearing and partial acceptance

1. **Price clearing.** Inframarginal steps are fully accepted. When a
   limit **equals** the clearing price, `MARGINAL_ACCEPT_FRACTION = 0.5`
   of that step is accepted. This is an **ASSUMED** tie-break: we do
   not have the SDAC residual supply/demand curve, so we cannot
   reproduce official volume matching at the margin.
2. **No simultaneous charge and discharge.** If both sides would
   clear, the volumes are netted.
3. **Physical partial acceptance.** The accepted MW is then walked
   through `apply_dispatch`, which clips to power and SoC. A fill that
   is cut back is labelled `soc_partial`.

The **locked-schedule** baseline is the current approach: solve the
cost-aware LP on P50 at gate closure and take a **price-taking** fill
at the realised clearing price (volume does not depend on how far the
realised price missed the forecast), still clipped to SoC.

## Backtest

Script: `packages/forecast/scripts/run_gate_closure_bidding.py`.

- Window: 2025-11-01 → 2026-10-30, sourced fee preset.
- `--forecast climatology` — causal 90-day hour-of-day P10/P50/P90
  (memory-light).
- `--forecast ml` — walk-forward quantile model, lookback 90 d, refit
  every 7 d, tight Mondrian CQR. **Price-only** in the published run
  (no fundamentals panel).
- Incremental value: moving-block bootstrap on daily net cash, block
  7 days, 400 draws, 90% percentile CI.

Measured numbers, including the honest negative result, live in
[`packages/forecast/results/GATE_CLOSURE_BIDDING.md`](../packages/forecast/results/GATE_CLOSURE_BIDDING.md).

**Headline:** on both fans, quantile bids and anchored bids
**underperformed** the locked cost-aware schedule, and the 90% CIs
exclude zero. Myopic hourly curves have no water value and under-cycle.
The locked intertemporal LP remains the better paper policy on this
window. The bidding code is kept because later layers (water-value
reservations, intraday re-optimisation, imbalance) need it.

## What this is not

- Not an exchange API, order gateway, or real bidding interface.
- Not a claim that 75,101 EUR (ML locked schedule in this experiment)
  replaces the published sourced cost-aware ML **65,473** EUR path.
  That published path used fundamentals and PaperAgent risk clips
  (411 cycles vs 479 here). Only same-fan bid-vs-schedule deltas are
  comparable.
- Not a substitute for official SDAC block-order / curve matching.

Paper trading only.
