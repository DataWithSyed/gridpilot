"""Column schemas, licence metadata, and light validation."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TZ = "Europe/Berlin"

PRICE_COLUMNS = ["da_price_eur_mwh"]
POWER_COLUMNS = [
    "load_mw",
    "residual_load_mw",
    "wind_onshore_mw",
    "wind_offshore_mw",
    "solar_mw",
]


@dataclass(frozen=True)
class SourceMeta:
    name: str
    url: str
    licence: str
    attribution: str
    notes: str = ""


SOURCES = {
    "energy_charts_price": SourceMeta(
        name="Energy-Charts day-ahead price (DE-LU)",
        url="https://api.energy-charts.info/v2/price",
        licence="CC BY 4.0",
        attribution="Bundesnetzagentur | SMARD.de (via Energy-Charts.info / Fraunhofer ISE)",
        notes="Only CC BY bidding zones are supported; response licence field is authoritative.",
    ),
    "energy_charts_power": SourceMeta(
        name="Energy-Charts public net generation",
        url="https://api.energy-charts.info/v2/public_power",
        licence="CC BY 4.0",
        attribution="Energy-Charts.info (Fraunhofer ISE)",
    ),
    "entsoe": SourceMeta(
        name="ENTSO-E Transparency Platform (optional)",
        url="https://transparency.entsoe.eu",
        licence="ENTSO-E terms; user token required",
        attribution="ENTSO-E Transparency Platform",
        notes="Token via ENTSOE_API_TOKEN env var only — never hardcode.",
    ),
}


def validate_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    missing = [c for c in PRICE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"price frame missing columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("price frame index must be DatetimeIndex")
    if df["da_price_eur_mwh"].isna().all():
        raise ValueError("all da_price_eur_mwh values are NaN")
    return df


def validate_power_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    present = [c for c in POWER_COLUMNS if c in df.columns]
    if not present:
        raise ValueError(f"power frame needs at least one of {POWER_COLUMNS}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("power frame index must be DatetimeIndex")
    return df
