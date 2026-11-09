# Data provenance (gitignored cache)

Prepared DE-LU hourly panel under `data/cache/` is **not** committed.

- Source API: [Energy-Charts](https://api.energy-charts.info) / SMARD
- Licence: **CC BY 4.0** (attribution: energy-charts.info)
- Contents: day-ahead price (`price`) + TSO day-ahead forecasts (`load_fc`, `solar_fc`, `wind_onshore_fc`, `wind_offshore_fc`)
- Built with the same public endpoints used by linked repo `de-day-ahead-price-forecasting` (`/price`, `/public_power_forecast` with `forecast_type=day-ahead`)
- Rebuild: `python packages/forecast/scripts/fetch_fundamentals.py --start YYYY-MM-DD --end YYYY-MM-DD`

Only CC BY zones (e.g. DE-LU) are supported.
