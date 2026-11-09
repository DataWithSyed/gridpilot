"""Energy-Charts DE-LU day-ahead price replay (CC BY 4.0).

Paper-trading / backtest only. Attributes Fraunhofer ISE Energy-Charts /
Bundesnetzagentur | SMARD.de. Refuses non-CC BY bidding zones.

Energy-Charts currently returns **15-minute** MTU for DE-LU. By default this
module resamples to **hourly means** so paper-trading with dt_h=1.0 is consistent.
Pass to_hourly=False to keep native resolution (then set PaperAgent dt_h=0.25).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

EC_BASE = "https://api.energy-charts.info"
TZ = "Europe/Berlin"
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"


def _chunk_bounds(start: str, end: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    month_starts = pd.date_range(s.normalize().replace(day=1), e, freq="MS")
    if len(month_starts) == 0 or month_starts[0] > s:
        month_starts = month_starts.insert(0, s.normalize().replace(day=1))
    out: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for i, a in enumerate(month_starts):
        b = (pd.Timestamp(month_starts[i + 1]) - pd.Timedelta(days=1)) if i + 1 < len(month_starts) else e
        a2, b2 = max(pd.Timestamp(a), s), min(pd.Timestamp(b), e)
        if a2 <= b2:
            out.append((a2, b2))
    return out


def _parse_price_payload(payload: dict) -> pd.DataFrame:
    licence = payload.get("license") or payload.get("licence") or ""
    rows = []
    for rec in payload.get("data") or []:
        vals = rec.get("values") or {}
        if "day_ahead_price" not in vals:
            continue
        rows.append(
            {
                "timestamp": rec.get("timestamp"),
                "da_price_eur_mwh": vals["day_ahead_price"],
                "_licence": licence,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["da_price_eur_mwh", "_licence"])
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(TZ, ambiguous="infer", nonexistent="shift_forward")
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(TZ)
    return df.set_index("timestamp").sort_index()


def fetch_day_ahead_prices(
    start: str,
    end: str,
    *,
    bzn: str = "DE-LU",
    cache_dir: Path | None = None,
    refresh: bool = False,
    timeout: float = 60.0,
    to_hourly: bool = True,
) -> pd.Series:
    """Return Europe/Berlin-indexed Series of DE-LU day-ahead prices (EUR/MWh)."""
    cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)
    parts: list[pd.DataFrame] = []
    for a, b in _chunk_bounds(start, end):
        dest = cache_dir / f"ec_v2_price_{bzn}_{a:%Y%m%d}_{b:%Y%m%d}.json"
        if dest.exists() and not refresh:
            payload = json.loads(dest.read_text(encoding="utf-8"))
        else:
            url = f"{EC_BASE}/v2/price?bzn={bzn}&start={a:%Y-%m-%d}&end={b:%Y-%m-%d}"
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            payload = r.json()
            dest.write_text(json.dumps(payload), encoding="utf-8")
        lic = payload.get("license") or ""
        if lic and "CC BY" not in lic.upper():
            raise RuntimeError(
                f"Bidding zone {bzn} price licence is not CC BY ({lic!r}). "
                "Only CC BY zones (e.g. DE-LU) are supported."
            )
        df = _parse_price_payload(payload)
        if not df.empty:
            parts.append(df)
    if not parts:
        return pd.Series(dtype=float, name="da_price_eur_mwh")
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    s = pd.Timestamp(start, tz=TZ)
    e = pd.Timestamp(end, tz=TZ) + pd.Timedelta(hours=23, minutes=59)
    sliced = out.loc[(out.index >= s) & (out.index <= e)]
    series = sliced["da_price_eur_mwh"].astype(float).rename("da_price_eur_mwh")
    if to_hourly and len(series) > 0:
        # Mean of 15-min MTUs → hourly price used for paper trading at dt_h=1
        series = series.resample("h").mean().dropna()
        series.name = "da_price_eur_mwh"
    return series


def load_or_fetch_prices(
    start: str,
    end: str,
    *,
    cache_dir: Path | None = None,
    refresh: bool = False,
    to_hourly: bool = True,
) -> pd.Series:
    return fetch_day_ahead_prices(
        start, end, cache_dir=cache_dir, refresh=refresh, to_hourly=to_hourly
    )
