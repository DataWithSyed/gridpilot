"""Scenario packs: historical replay (attributed) and clearly-labelled synthetic series."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

SourceKind = Literal["energy_charts", "synthetic"]


@dataclass(frozen=True)
class Scenario:
    name: str
    kind: SourceKind
    prices: pd.Series  # tz-aware Europe/Berlin hourly DA prices
    description: str
    seed: int | None = None
    attribution: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_meta(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "seed": self.seed,
            "attribution": self.attribution,
            "notes": list(self.notes),
            "n_hours": int(len(self.prices)),
            "start": str(self.prices.index[0]) if len(self.prices) else None,
            "end": str(self.prices.index[-1]) if len(self.prices) else None,
            "synthetic": self.kind == "synthetic",
        }


def _berlin_index(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=periods, freq="h", tz="Europe/Berlin")


def _synthetic_base(index: pd.DatetimeIndex, seed: int, mean: float = 90.0) -> pd.Series:
    rng = np.random.default_rng(seed)
    hour = np.array([t.hour for t in index])
    # Mild diurnal shape, deterministic given seed
    diurnal = 25.0 * np.sin((hour - 8) / 24.0 * 2 * np.pi)
    noise = rng.normal(0.0, 6.0, size=len(index))
    return pd.Series(mean + diurnal + noise, index=index, name="da_price_eur_mwh")


def scenario_normal(*, seed: int = 0, days: int = 7) -> Scenario:
    idx = _berlin_index("2026-01-05", days * 24)
    px = _synthetic_base(idx, seed, mean=92.0)
    return Scenario(
        name="normal",
        kind="synthetic",
        prices=px,
        seed=seed,
        description="SYNTHETIC quiet winter week (labelled; not Energy-Charts).",
        notes=("Clearly synthetic. For demos and tests, not a market result.",),
    )


def scenario_price_spike(*, seed: int = 1, days: int = 7) -> Scenario:
    idx = _berlin_index("2026-01-05", days * 24)
    px = _synthetic_base(idx, seed, mean=100.0)
    # Spike on day 4 afternoon
    spike = (idx.normalize() == (idx[0] + pd.Timedelta(days=3)).normalize()) & (idx.hour >= 16) & (idx.hour <= 20)
    px = px.copy()
    px.loc[spike] = [480.0, 620.0, 540.0, 390.0, 260.0][: int(spike.sum())]
    return Scenario(
        name="price_spike",
        kind="synthetic",
        prices=px,
        seed=seed,
        description="SYNTHETIC evening price spike (labelled; not Energy-Charts).",
        notes=("Injected 480–620 €/MWh spike on day 4 16–20h Berlin.",),
    )


def scenario_negative_prices(*, seed: int = 2, days: int = 7) -> Scenario:
    idx = _berlin_index("2026-01-05", days * 24)
    px = _synthetic_base(idx, seed, mean=70.0)
    px = px.copy()
    midday = (idx.hour >= 11) & (idx.hour <= 15)
    # Negative on days 2–3 midday
    days23 = (idx.day_of_year >= idx[0].day_of_year + 1) & (idx.day_of_year <= idx[0].day_of_year + 2)
    px.loc[midday & days23] = -35.0 + _synthetic_base(idx, seed + 99, mean=0.0).loc[midday & days23]
    return Scenario(
        name="negative_prices",
        kind="synthetic",
        prices=px,
        seed=seed,
        description="SYNTHETIC negative midday prices (labelled; not Energy-Charts).",
        notes=("Hours 11–15 on days 2–3 set near −35 €/MWh.",),
    )


def scenario_data_outage(*, seed: int = 3, days: int = 7) -> Scenario:
    idx = _berlin_index("2026-01-05", days * 24)
    px = _synthetic_base(idx, seed, mean=88.0)
    px = px.copy()
    # Six-hour outage on day 3
    out = (idx.normalize() == (idx[0] + pd.Timedelta(days=2)).normalize()) & (idx.hour >= 8) & (idx.hour <= 13)
    px.loc[out] = np.nan
    return Scenario(
        name="data_outage",
        kind="synthetic",
        prices=px,
        seed=seed,
        description="SYNTHETIC feed outage (NaN prices for 6 hours; labelled).",
        notes=("Agent must hold through missing ticks; no invented fills.",),
    )


def scenario_forecast_failure(*, seed: int = 4, days: int = 7) -> Scenario:
    idx = _berlin_index("2026-01-05", days * 24)
    px = _synthetic_base(idx, seed, mean=95.0)
    return Scenario(
        name="forecast_failure",
        kind="synthetic",
        prices=px,
        seed=seed,
        description="SYNTHETIC week used with a deliberately broken forecast (bias +80 €/MWh).",
        notes=(
            "Prices themselves are a quiet synthetic week; the engine applies a forecast bias.",
            "Used to stress-test decisions under a failed forecast, not as market data.",
        ),
    )


def load_historical_window(path: Path, start: str, end: str) -> pd.Series:
    df = pd.read_csv(path, parse_dates=[0], index_col=0)
    s = df.iloc[:, 0].astype(float)
    s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Berlin")
    s = s.resample("h").mean().rename("da_price_eur_mwh")
    return s.loc[start:end].dropna()


def scenario_historical(
    cache: Path,
    *,
    start: str = "2026-01-05",
    end: str = "2026-01-11 23:00",
    name: str = "historical",
) -> Scenario:
    px = load_historical_window(cache, start, end)
    if px.empty:
        raise FileNotFoundError(f"no prices in {cache} for {start}–{end}")
    return Scenario(
        name=name,
        kind="energy_charts",
        prices=px,
        description=f"Energy-Charts DE-LU day-ahead replay {start} → {end}.",
        attribution="Energy-Charts / SMARD — CC BY 4.0",
        notes=("Historical public prices only. Paper replay; not a live feed.",),
    )


SCENARIO_BUILDERS = {
    "normal": scenario_normal,
    "price_spike": scenario_price_spike,
    "negative_prices": scenario_negative_prices,
    "data_outage": scenario_data_outage,
    "forecast_failure": scenario_forecast_failure,
}

SCENARIOS = tuple(SCENARIO_BUILDERS)


def load_scenario(name: str, *, seed: int = 0, **kwargs) -> Scenario:
    key = name.strip().lower()
    if key in {"historical", "energy_charts"}:
        cache = Path(kwargs.pop("cache"))
        return scenario_historical(cache, **kwargs)
    if key not in SCENARIO_BUILDERS:
        known = ", ".join([*SCENARIO_BUILDERS, "historical"])
        raise ValueError(f"Unknown scenario {name!r}. Known: {known}")
    fn = SCENARIO_BUILDERS[key]
    # builders accept seed (and days)
    return fn(seed=seed, **{k: v for k, v in kwargs.items() if k in {"days"}})
