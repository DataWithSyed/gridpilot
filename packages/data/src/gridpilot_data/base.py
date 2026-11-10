"""Adapter protocol."""
from __future__ import annotations

from typing import Protocol

import pandas as pd


class PriceAdapter(Protocol):
    name: str

    def fetch_day_ahead_prices(
        self,
        start: str,
        end: str,
        *,
        refresh: bool = False,
        to_hourly: bool = True,
    ) -> pd.Series: ...


class PowerAdapter(Protocol):
    name: str

    def fetch_public_power(
        self,
        start: str,
        end: str,
        *,
        refresh: bool = False,
        to_hourly: bool = True,
    ) -> pd.DataFrame: ...
