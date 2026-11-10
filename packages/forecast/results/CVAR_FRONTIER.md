# Cost-aware CVaR frontier (paper only)

Window: 2025-11-01 → 2026-10-30 (364 days, 8736 hours).
Costs: sourced preset. Scenarios: causal last-60 Berlin daily price paths, hour-aligned. CVaR level α=5%.
Objective: maximise E[cash] − λ CVaR_α(loss). Out-of-sample figures below are from the locked plan settled at realised DA.

| λ | Net EUR | Mean €/day | OOS CVaR₅% loss € |
| ---: | ---: | ---: | ---: |
| 0 | 69621.92 | 191.27 | 18.56 |
| 0.5 | 68904.56 | 189.30 | 11.47 |
| 1 | 67863.80 | 186.44 | 9.09 |
| 2 | 66717.69 | 183.29 | 6.34 |
| 5 | 63742.86 | 175.12 | 6.68 |
| 10 | 61177.95 | 168.07 | 4.21 |

Highest net cash: λ=0 at 69621.92 EUR (CVaR₅% 18.56).
Lowest OOS CVaR₅% loss: λ=10 at 4.21 EUR (cash 61177.95).

These points are a discrete efficient-frontier sample, not a continuous curve. Higher λ is not guaranteed to improve *out-of-sample* CVaR. Paper trading only.

**What improved:** moving from λ=0 to λ=1–2 cuts out-of-sample CVaR₅% of loss by more than half (18.56 → 9.09 / 6.34) for a modest cash concession (69,622 → 67,864 / 66,718).

**What did not:** λ=5 is **not** better than λ=2 on OOS CVaR (6.68 vs 6.34) and earns less cash. The sample is a discrete frontier, not a guarantee that more risk aversion is better out of sample.

These figures are not a re-run of the published sourced cost-aware ML 65,473 EUR path (different forecast and risk clips).

