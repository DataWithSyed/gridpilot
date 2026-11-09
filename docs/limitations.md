# Limitations

- Paper trading / research only — no live order placement.
- Block bootstrap preserves within-block dependence but **understates** structural regime shifts.
- VaR/CVaR here are **historical** on the scenario (or daily PnL) sample, not parametric.
- Default block length (7 days) and scenario count are **ASSUMED** and should be stress-tested.
- Coupling to `gridpilot-core.PaperAgent` is optional; demos may use toy PnL proxies — prefer real agent cash for reported figures.
