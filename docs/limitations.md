# Limitations

- Paper trading only — no live orders.
- `RollingQuantilePriceForecast` is a **hour-of-day climatology**, not a trained ML forecaster.
- Walk-forward over a short window still has **warm-up** effects in the first lookback days.
- LP plans ignore fees, imbalance, and order-book microstructure (ASSUMED zero unless labelled).
- Risk-aware blend weights are **ASSUMED**.
