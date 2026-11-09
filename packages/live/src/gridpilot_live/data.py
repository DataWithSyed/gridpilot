"""Fetch / extend near-live Energy-Charts fundamentals for the pilot."""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

EC_BASE = "https://api.energy-charts.info"
FORECAST_TYPES = ("load", "solar", "wind_onshore", "wind_offshore")
TZ_BERLIN = "Europe/Berlin"


def _get(endpoint: str, params: dict, max_tries: int = 12) -> dict:
    for _ in range(max_tries):
        r = requests.get(f"{EC_BASE}/{endpoint}", params=params, timeout=120)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "40")) + 2
            time.sleep(wait)
            continue
        if r.status_code == 404:
            raise FileNotFoundError(f"no content for {endpoint} {params}")
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"gave up on {endpoint} {params}")


def _to_hourly(unix_seconds, values, name: str) -> pd.Series:
    idx = pd.to_datetime(unix_seconds, unit="s", utc=True)
    s = pd.Series(values, index=idx, name=name, dtype="float64")
    return s.resample("1h").mean()


def latest_published_price_day(bzn: str = "DE-LU") -> pd.Timestamp:
    """Return the last Berlin calendar day with published day-ahead prices.

    Day-ahead prices for delivery day D are typically published on D-1 after
    SDAC clears (~13:00 CET). Near midnight Berlin time, tomorrow's curve may
    already be public, so we probe a small forward window as well as back.
    """
    today = pd.Timestamp.now(tz=TZ_BERLIN).normalize()
    best = None
    # Probe tomorrow..today-4 (DA for D is often up on D-1 afternoon)
    for delta in range(2, -5, -1):
        d = (today + pd.Timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            payload = _get("price", {"bzn": bzn, "start": d, "end": d})
        except Exception:
            continue
        secs = payload.get("unix_seconds") or []
        if not secs:
            continue
        idx = pd.to_datetime(secs, unit="s", utc=True).tz_convert(TZ_BERLIN)
        day = pd.Timestamp(idx.max().date())
        if best is None or day > best:
            best = day
    if best is None:
        raise RuntimeError("could not find any recent published DE-LU day-ahead prices")
    return best


def fetch_window(start: str, end: str, *, sleep_s: float = 0.4) -> pd.DataFrame:
    """Fetch price + day-ahead fundamentals for [start, end] (inclusive calendar days)."""
    cols = []
    p = _get("price", {"bzn": "DE-LU", "start": start, "end": end})
    lic = (p.get("license") or p.get("licence") or "")
    if lic and "CC BY" not in lic.upper():
        raise RuntimeError(f"Non-CC BY licence for prices: {lic!r}")
    cols.append(_to_hourly(p["unix_seconds"], p["price"], "price"))
    for pt in FORECAST_TYPES:
        try:
            f = _get(
                "public_power_forecast",
                {
                    "country": "de",
                    "production_type": pt,
                    "forecast_type": "day-ahead",
                    "start": start,
                    "end": end,
                },
            )
            cols.append(_to_hourly(f["unix_seconds"], f["forecast_values"], f"{pt}_fc"))
        except FileNotFoundError:
            # Leave column missing; caller may ffill from prior cache.
            pass
        time.sleep(sleep_s)
    return pd.concat(cols, axis=1).sort_index()


def load_or_extend_fundamentals(
    *,
    base_cache: Path,
    out_cache: Path,
    end: str,
    lookback_start: str,
    refresh_tail: bool = True,
) -> pd.DataFrame:
    """Merge an existing fundamentals cache with a freshly fetched tail through ``end``."""
    base_cache = Path(base_cache)
    out_cache = Path(out_cache)
    out_cache.parent.mkdir(parents=True, exist_ok=True)

    if base_cache.exists():
        df = pd.read_csv(base_cache, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
    else:
        df = fetch_window(lookback_start, end)
        df.index.name = "time_utc"
        df.to_csv(out_cache, compression="gzip")
        return df

    last = df.index.max()
    end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    if refresh_tail and last < end_ts:
        # Start one day before last full day to overwrite a possibly partial day.
        start_fetch = (last.tz_convert("UTC") - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            tail = fetch_window(start_fetch, end)
        except Exception as exc:  # noqa: BLE001 — report soft failure to caller
            # Keep stale cache but annotate via empty attr
            df.attrs["extend_error"] = str(exc)
            return df
        if not tail.empty:
            df = pd.concat([df, tail]).sort_index()
            df = df[~df.index.duplicated(keep="last")]
    # Trim to lookback_start for memory, keep a bit of headroom
    start_ts = pd.Timestamp(lookback_start, tz="UTC") - pd.Timedelta(days=5)
    df = df.loc[df.index >= start_ts].copy()
    need = ["price", "load_fc", "solar_fc", "wind_onshore_fc", "wind_offshore_fc"]
    for c in need:
        if c not in df.columns:
            df[c] = pd.NA
    # Ex-ante safe: forward-fill fund forecasts by at most 1 day of hours
    for c in need[1:]:
        df[c] = df[c].ffill(limit=24)
    df.index.name = "time_utc"
    df.to_csv(out_cache, compression="gzip")
    return df
