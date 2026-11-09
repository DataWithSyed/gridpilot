"""Pluggable adapter classes wrapping fetch helpers."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from gridpilot_data import energy_charts as ec
from gridpilot_data.cache import ensure_dir
from gridpilot_data.schema import TZ, validate_price_frame


class EnergyChartsAdapter:
    """Live / near-live Energy-Charts DE-LU prices + DE public power."""

    name = "energy_charts"

    def __init__(self, cache_dir: Path | None = None, bzn: str = "DE-LU", country: str = "de") -> None:
        self.cache_dir = ensure_dir(cache_dir)
        self.bzn = bzn
        self.country = country

    def fetch_day_ahead_prices(
        self, start: str, end: str, *, refresh: bool = False, to_hourly: bool = True
    ) -> pd.Series:
        return ec.fetch_day_ahead_prices(
            start, end, bzn=self.bzn, cache_dir=self.cache_dir, refresh=refresh, to_hourly=to_hourly
        )

    def fetch_public_power(
        self, start: str, end: str, *, refresh: bool = False, to_hourly: bool = True
    ) -> pd.DataFrame:
        return ec.fetch_public_power(
            start, end, country=self.country, cache_dir=self.cache_dir, refresh=refresh, to_hourly=to_hourly
        )


class ReplayAdapter:
    """Replay from a pre-fetched price series (CSV/Parquet/Series) — offline paper trading."""

    name = "replay"

    def __init__(self, prices: pd.Series | Path | str) -> None:
        if isinstance(prices, (str, Path)):
            path = Path(prices)
            if path.suffix.lower() == ".parquet":
                s = pd.read_parquet(path).squeeze()
            else:
                df = pd.read_csv(path, parse_dates=[0], index_col=0)
                s = df.iloc[:, 0]
            self._prices = s.astype(float)
        else:
            self._prices = prices.astype(float)
        if self._prices.index.tz is None:
            self._prices.index = self._prices.index.tz_localize(TZ, ambiguous="infer", nonexistent="shift_forward")
        else:
            self._prices.index = self._prices.index.tz_convert(TZ)
        self._prices = self._prices.sort_index().rename("da_price_eur_mwh")

    def fetch_day_ahead_prices(
        self, start: str, end: str, *, refresh: bool = False, to_hourly: bool = True
    ) -> pd.Series:
        _ = refresh
        s = pd.Timestamp(start, tz=TZ)
        e = pd.Timestamp(end, tz=TZ) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        out = self._prices.loc[(self._prices.index >= s) & (self._prices.index <= e)]
        if to_hourly and not out.empty:
            # already hourly in most caches; mean-resample is idempotent for hourly
            out = out.resample("h").mean()
        validate_price_frame(out.to_frame())
        return out


class EntsoeAdapter:
    """Optional ENTSO-E day-ahead prices. Token from ENTSOE_API_TOKEN only.

    Never hardcodes credentials. Without the env var, construction raises.
    Requires optional dependency ``entsoe-py`` (``pip install gridpilot-data[entsoe]``).
    """

    name = "entsoe"

    def __init__(self, cache_dir: Path | None = None, area: str = "DE_LU") -> None:
        token = os.environ.get("ENTSOE_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "ENTSOE_API_TOKEN is not set. Export your Transparency Platform token "
                "in the environment; it is never stored in this repository."
            )
        try:
            from entsoe import EntsoePandasClient  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "entsoe-py is not installed. Install with: pip install 'gridpilot-data[entsoe]'"
            ) from exc
        self._client = EntsoePandasClient(api_key=token)
        self.cache_dir = ensure_dir(cache_dir)
        self.area = area

    def fetch_day_ahead_prices(
        self, start: str, end: str, *, refresh: bool = False, to_hourly: bool = True
    ) -> pd.Series:
        _ = refresh
        s = pd.Timestamp(start, tz=TZ)
        e = pd.Timestamp(end, tz=TZ) + pd.Timedelta(days=1)
        raw = self._client.query_day_ahead_prices(self.area, start=s, end=e)
        ser = raw.astype(float).rename("da_price_eur_mwh")
        if ser.index.tz is None:
            ser.index = ser.index.tz_localize(TZ)
        else:
            ser.index = ser.index.tz_convert(TZ)
        if to_hourly and not ser.empty:
            ser = ser.resample("h").mean()
        validate_price_frame(ser.to_frame())
        return ser
