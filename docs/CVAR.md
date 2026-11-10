# Cost-aware CVaR LP and return-vs-CVaR frontier (paper only)

A here-and-now daily schedule is chosen against causal price scenarios
with sourced `ExecutionCosts` inside every scenario cash path. The
Rockafellar–Uryasev LP maximises `E[cash] − λ CVaR_α(loss)` with
`α = 5%` (worst 5% tail). It never places real orders.

## Scenarios

The published run uses the last **60** completed Berlin days of realised
DA prices, hour-aligned onto tomorrow (strictly causal). This is a
climatology-of-paths assumption, not a fitted stochastic-volatility
model. Days with 23/25 hours are mapped by clock hour.

## Frontier (2025-11-01 → 2026-10-30, sourced fees, 8,736 h)

Out-of-sample: the locked plan is settled at the realised DA price.

| λ | Net EUR | Mean €/day | OOS CVaR₅% loss € |
| ---: | ---: | ---: | ---: |
| 0 | 69,622 | 191.27 | 18.56 |
| 0.5 | 68,905 | 189.30 | 11.47 |
| 1 | 67,864 | 186.44 | 9.09 |
| 2 | 66,718 | 183.29 | 6.34 |
| 5 | 63,743 | 175.12 | 6.68 |
| 10 | 61,178 | 168.07 | 4.21 |

Raising λ from 0 to 2 cuts OOS CVaR₅% from 18.56 to **6.34** for a
**2,904 EUR** drop in net cash. λ=10 reaches the lowest CVaR (4.21)
at 61,178 EUR. **λ=5 did not improve OOS CVaR versus λ=2** (6.68 vs
6.34) while giving up another ~3k EUR — the out-of-sample frontier is
not perfectly monotone.

These cash totals are **not** comparable to the published sourced
cost-aware ML path (65,473 EUR), which used a different forecast
(fundamentals + ML + CQR) and PaperAgent cycle clips. λ=0 here is an
expected-value LP on 60 historical paths, not that ML agent.

Reproduce:

```bash
python packages/forecast/scripts/run_cvar_frontier.py --costs sourced
```

Code: `gridpilot_forecast.cvar_lp.solve_day_lp_cvar`. Results:
[`packages/forecast/results/CVAR_FRONTIER.md`](../packages/forecast/results/CVAR_FRONTIER.md).
Paper trading only.
