# Limitations (umbrella)

Honest scope limits. This page is not a results table; numbers live in [RESULTS.md](RESULTS.md).

- **Paper trading only.** There is no exchange or broker adapter, and no path that places or signs real orders. Paper cash is not real-money performance. Star counts are not a project goal in these docs.
- **Day-ahead first.** The published agent is an hourly DE-LU day-ahead paper model with 15-minute MTUs averaged to hourly means. It is not a full multi-market EMS.
- **Coverage is still below 80%.** On the 12-month window, tight Mondrian reached **78.9%** against a nominal 80% P10–P90 band (raw 50.0%, rolling CQR 72.2%). The 14-day live pilot re-run on 2026-11-10 printed **52.4%**. Better calibration has not automatically raised paper profit.
- **No public intraday or official reBAP series** in the published runs. Energy-Charts has no ID / ID-index endpoint that returns a distinct series (checked 2026-11-10). Official reBAP requires Netztransparenz Extranet OAuth and was not fetchable. The ID layer is labelled **proxy-only** (`PROXY_ID_EQ_DA`, `PROXY_REBAP_EQ_DA`).
- **Degradation remains ASSUMED at 5 €/MWh** of throughput. It is not a published tariff, and it dominates the sourced-fee cost line (for example cost-aware ML paid €8,219 degradation versus €25 fees).
- **Bid curves still trail the locked schedule.** Water-value reservations (2026-11-14 climatology re-run) improved on myopic quantile bids (13,082 → 30,675 €; +48.33 [39.45, 58.87] €/day) but still lost to the lock (60,379 €; −81.60 [−99.12, −61.52] €/day). Both CIs exclude zero. See [BIDDING.md](BIDDING.md).
- **Sourced DA fee is a lower bound.** It is ECC Lux clearing only (0.015 €/MWh). The current EPEX trading fee was not in the public 2026 price list and is omitted. Annual ECC membership is documented in [fees.md](fees.md) and is not amortised into the per-MWh preset.
- **Oracle and experiment paths are not interchangeable.** Perfect foresight is not tradeable. Bid-curve, ID, and CVaR cash use fans or clip settings that differ from the published cost-aware ML **65,473 €** path (8,735 h, fundamentals, PaperAgent clips).
- **CVaR out-of-sample is not monotone in λ.** On the published frontier, λ = 5 did not beat λ = 2 on out-of-sample CVaR₅% (6.68 versus 6.34).
- Forecast features in current published 12-month ML runs include **day-ahead TSO load / solar / wind** when the Energy-Charts forecast feed is used. Older short-window package READMEs (2026-08-01 → 2026-10-15) may still describe a price-only or climatology setup for *that* window — those figures are historical, not a description of the 12-month path.
- Risk P50/P90 in `packages/core` are descriptive daily-PnL percentiles; scenario VaR/CVaR lives in `packages/risk` and in the CVaR LP.
- The dashboard and simulator UI need Streamlit (`pip install -e ".[dev,ui]"`). Shared research computers can be tight on memory; prefer committed result files over re-running a 12-month walk-forward to edit documentation.
