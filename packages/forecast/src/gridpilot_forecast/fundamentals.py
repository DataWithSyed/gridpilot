"""Energy-Charts day-ahead fundamentals for ex-ante price features.

Prefers TSO **day-ahead** forecasts of load / solar / wind (available before
SDAC gate closure on D-1). If a day-ahead forecast series is missing, falls
back to **lagged actuals** (D-1 profile) and labels them — never same-day
actuals (that would leak).

Fetch pattern mirrors epm-data-pipeline / de-day-ahead-price-forecasting
(Energy-Charts public API, CC BY 4.0 only).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from gridpilot_forecast.features import TZ, daily_panel, to_berlin

EC_BASE = "https://api.energy-charts.info"
FORECAST_TYPES = ("load", "solar", "wind_onshore", "wind_offshore")
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"


def _get(endpoint: str, params: dict, max_tries: int = 12) -> dict:
    for _ in range(max_tries):
        r = requests.get(f"{EC_BASE}/{endpoint}", params=params, timeout=120)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "40")) + 2
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"gave up on {endpoint} {params}")


def _to_hourly(unix_seconds, values, name: str) -> pd.Series:
    idx = pd.to_datetime(unix_seconds, unit="s", utc=True)
    s = pd.Series(values, index=idx, name=name, dtype="float64")
    return s.resample("1h").mean()


def fetch_fundamentals(
    start: str,
    end: str,
    *,
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch DE-LU DA prices + DE day-ahead load/solar/wind forecasts (hourly UTC).

    Returns columns: price, load_fc, solar_fc, wind_onshore_fc, wind_offshore_fc.
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"de_lu_hourly_{start}_{end}.csv.gz"
    if dest.exists() and not refresh:
        return load_fundamentals(dest)

    # Year chunks keep payloads small (Energy-Charts rate limits ~2 req/min).
    years = range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)
    parts: list[pd.DataFrame] = []
    for y in years:
        a = max(pd.Timestamp(start), pd.Timestamp(f"{y}-01-01")).strftime("%Y-%m-%d")
        b = min(pd.Timestamp(end), pd.Timestamp(f"{y}-12-31")).strftime("%Y-%m-%d")
        cols = []
        p = _get("price", {"bzn": "DE-LU", "start": a, "end": b})
        lic = (p.get("license") or p.get("licence") or "")
        # v1 price payload may omit licence; DE-LU is documented CC BY via SMARD.
        if lic and "CC BY" not in lic.upper():
            raise RuntimeError(f"Non-CC BY licence for prices: {lic!r}")
        cols.append(_to_hourly(p["unix_seconds"], p["price"], "price"))
        for pt in FORECAST_TYPES:
            f = _get(
                "public_power_forecast",
                {
                    "country": "de",
                    "production_type": pt,
                    "forecast_type": "day-ahead",
                    "start": a,
                    "end": b,
                },
            )
            cols.append(_to_hourly(f["unix_seconds"], f["forecast_values"], f"{pt}_fc"))
            time.sleep(0.5)  # be polite to the API
        parts.append(pd.concat(cols, axis=1))
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.index.name = "time_utc"
    df.to_csv(dest, compression="gzip")
    # Also refresh the generic cache name used by eval scripts
    generic = cache_dir / "de_lu_hourly.csv.gz"
    df.to_csv(generic, compression="gzip")
    return df


def load_fundamentals(path: Path | str | None = None) -> pd.DataFrame:
    path = Path(path or (DEFAULT_CACHE / "de_lu_hourly.csv.gz"))
    if not path.exists():
        raise FileNotFoundError(
            f"No fundamentals cache at {path}. Run scripts/fetch_fundamentals.py first."
        )
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def slice_window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    out = df.loc[(df.index >= s) & (df.index <= e)].copy()
    return out


def series_to_panel(s: pd.Series) -> pd.DataFrame:
    """Hourly series → local-date × hour panel (Berlin)."""
    return daily_panel(s.rename("x") if s.name is None else s)


def build_fundamentals_panels(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build day×hour panels. Forecast series may be ffilled 1 day (ex-ante safe).

    Price panel is never forward-filled across days.
    """
    need = ["price", "load_fc", "solar_fc", "wind_onshore_fc", "wind_offshore_fc"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"fundamentals frame missing columns: {missing}")
    panels: dict[str, pd.DataFrame] = {}
    for col in need:
        pan = series_to_panel(df[col])
        if col != "price":
            pan = pan.ffill(limit=1)
        panels[col] = pan
    # Residual load from day-ahead forecasts (ex-ante)
    panels["residual_load_fc"] = (
        panels["load_fc"]
        - panels["solar_fc"]
        - panels["wind_onshore_fc"]
        - panels["wind_offshore_fc"]
    )
    panels["wind_fc"] = panels["wind_onshore_fc"] + panels["wind_offshore_fc"]
    return panels


def lagged_actual_panels_from_public_power(
    power: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """ASSUMED fallback: use D-1 actual load/renewables as if they were D0 forecasts.

    Labelled lagged — must not be treated as same-day actuals.
    ``power`` columns expected: load_mw, solar_mw, wind_onshore_mw, wind_offshore_mw
    (Energy-Charts public_power actuals).
    """
    rename = {
        "load_mw": "load_fc",
        "solar_mw": "solar_fc",
        "wind_onshore_mw": "wind_onshore_fc",
        "wind_offshore_mw": "wind_offshore_fc",
    }
    panels = {}
    for src, dst in rename.items():
        if src not in power.columns:
            continue
        pan = series_to_panel(power[src])
        # Shift by 1 calendar day → D-1 actual becomes D0 "forecast" proxy
        pan = pan.shift(1, freq="D")
        panels[dst] = pan
    if "load_fc" in panels and "solar_fc" in panels and "wind_onshore_fc" in panels and "wind_offshore_fc" in panels:
        panels["wind_fc"] = panels["wind_onshore_fc"] + panels["wind_offshore_fc"]
        panels["residual_load_fc"] = panels["load_fc"] - panels["solar_fc"] - panels["wind_fc"]
    return panels  # source label: lagged_actuals_D-1 (caller must document)


def assert_no_lookahead_price(panel: pd.DataFrame, day: pd.Timestamp, features_day: pd.Timestamp) -> None:
    """Raise if feature construction for ``features_day`` could see ``day`` prices."""
    day = pd.Timestamp(day).normalize()
    features_day = pd.Timestamp(features_day).normalize()
    if features_day >= day:
        raise AssertionError(
            f"Look-ahead: features for {features_day.date()} must not use price day {day.date()}"
        )
