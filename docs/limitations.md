# Limitations

- **Paper-trading / research feeds only.** No order placement.
- Energy-Charts DE-LU prices are **CC BY 4.0**; other bidding zones are refused when the response licence is not CC BY.
- Native MTU is often **15 minutes**; adapters default to **hourly mean** resampling.
- ENTSO-E adapter is **optional** and requires `ENTSOE_API_TOKEN` in the environment plus `entsoe-py`. Tokens are never committed.
- No fees, imbalance, or OTC products.
