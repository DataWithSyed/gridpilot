# Limitations (umbrella)

- No live trading. Ever, in this series' public code.
- Star counts are not a project goal written into docs or READMEs.
- Core v0.1 is day-ahead hourly paper trading with two baselines — not a full multi-market EMS.
- Risk P50/P90 in core are descriptive percentiles; full VaR/CVaR scenario engines belong in `gridpilot-risk`.
- Shared research computer resources may delay heavy forecast / dashboard steps; modules stay lean.


## packages/forecast / backtest / dashboard (2026-11-10)

- Forecast features are **price-lag + calendar only** (no TSO load/solar/wind day-ahead forecasts). Stronger feature set is in `de-day-ahead-price-forecasting`.
- Demo window 2026-08-01→2026-10-15 is short; ML train history is limited.
- ML models refit every 3 delivery days in the measured agent run (ASSUMED).
- Paper trading only; no fees, no slippage, hourly resample of 15-min MTU.
- Dashboard requires optional Streamlit (`pip install -e "packages/dashboard[ui]"`).
