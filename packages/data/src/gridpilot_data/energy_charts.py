"""Energy-Charts v2 live/near-live adapters (CC BY 4.0)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from gridpilot_data.cache import ensure_dir, read_json, write_json
from gridpilot_data.schema import TZ, validate_power_frame, validate_price_frame

EC_BASE = "https://api.energy-charts.info"

POWER_SERIES = {
    "load": "load_mw",
    "residual_load": "residual_load_mw",
    "wind_onshore": "wind_onshore_mw",
    "wind_offshore": "wind_offshore_mw",
    "solar": "solar_mw",
}


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


def _parse_v2(payload: dict, value_map: dict[str, str]) -> pd.DataFrame:
    licence = payload.get("license") or payload.get("licence") or ""
    rows = []
    for rec in payload.get("data") or []:
        vals = rec.get("values") or {}
        row = {"timestamp": rec.get("timestamp"), "_licence": licence}
        for src, dst in value_map.items():
            if src in vals:
                row[dst] = vals[src]
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(TZ, ambiguous="infer", nonexistent="shift_forward")
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(TZ)
    return df.set_index("timestamp").sort_index()


def _assert_cc_by(payload: dict, bzn: str) -> None:
    lic = payload.get("license") or payload.get("licence") or ""
    if lic and "CC BY" not in lic.upper():
        raise RuntimeError(
            f"Bidding zone {bzn} licence is not CC BY ({lic!r}). "
            "Only CC BY zones (e.g. DE-LU) are supported."
        )


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
    cache_dir = ensure_dir(cache_dir)
    parts: list[pd.DataFrame] = []
    for a, b in _chunk_bounds(start, end):
        dest = cache_dir / f"ec_v2_price_{bzn}_{a:%Y%m%d}_{b:%Y%m%d}.json"
        if dest.exists() and not refresh:
            payload = read_json(dest)
        else:
            url = f"{EC_BASE}/v2/price?bzn={bzn}&start={a:%Y-%m-%d}&end={b:%Y-%m-%d}"
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            payload = r.json()
            write_json(dest, payload)
        _assert_cc_by(payload, bzn)
        df = _parse_v2(payload, {"day_ahead_price": "da_price_eur_mwh"})
        if not df.empty:
            parts.append(df)
    if not parts:
        return pd.Series(dtype=float, name="da_price_eur_mwh")
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    s = pd.Timestamp(start, tz=TZ)
    e = pd.Timestamp(end, tz=TZ) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    out = out.loc[(out.index >= s) & (out.index <= e)]
    if to_hourly and not out.empty:
        out = out[["da_price_eur_mwh"]].resample("h").mean()
    validate_price_frame(out)
    return out["da_price_eur_mwh"].rename("da_price_eur_mwh")


def fetch_public_power(
    start: str,
    end: str,
    *,
    country: str = "de",
    cache_dir: Path | None = None,
    refresh: bool = False,
    timeout: float = 60.0,
    to_hourly: bool = True,
) -> pd.DataFrame:
    cache_dir = ensure_dir(cache_dir)
    parts: list[pd.DataFrame] = []
    for a, b in _chunk_bounds(start, end):
        dest = cache_dir / f"ec_v2_power_{country}_{a:%Y%m%d}_{b:%Y%m%d}.json"
        if dest.exists() and not refresh:
            payload = read_json(dest)
        else:
            url = f"{EC_BASE}/v2/public_power?country={country}&start={a:%Y-%m-%d}&end={b:%Y-%m-%d}"
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            payload = r.json()
            write_json(dest, payload)
        df = _parse_v2(payload, POWER_SERIES)
        if not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame(columns=list(POWER_SERIES.values()))
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    s = pd.Timestamp(start, tz=TZ)
    e = pd.Timestamp(end, tz=TZ) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    out = out.loc[(out.index >= s) & (out.index <= e)]
    cols = [c for c in POWER_SERIES.values() if c in out.columns]
    out = out[cols]
    if to_hourly and not out.empty:
        out = out.resample("h").mean()
    return validate_power_frame(out)
