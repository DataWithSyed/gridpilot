"""Virtual market clock with adjustable replay speed.

``speed`` is simulated seconds per wall-clock second (1, 60, 1000, ...).
``speed=0`` runs as fast as possible (tests, reports, demos).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

GATE_CLOSURE_HOUR_BERLIN = 12  # 12:00 CET/CEST (Europe/Berlin)


def as_berlin(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("Europe/Berlin")
    return t.tz_convert("Europe/Berlin")


def delivery_day(ts: pd.Timestamp) -> pd.Timestamp:
    b = as_berlin(ts)
    return b.normalize()


def gate_closure_for(delivery: pd.Timestamp) -> pd.Timestamp:
    """DA gate closure for a delivery day: 12:00 Europe/Berlin on D-1."""
    d = delivery_day(delivery)
    return (d - pd.Timedelta(days=1)).replace(hour=GATE_CLOSURE_HOUR_BERLIN, minute=0, second=0, microsecond=0)


def is_gate_closure_tick(ts: pd.Timestamp) -> bool:
    b = as_berlin(ts)
    return b.hour == GATE_CLOSURE_HOUR_BERLIN and b.minute == 0


DA_PUBLICATION_HOUR_BERLIN = 13  # first hourly tick after ~12:45 D-1 publication


def is_da_publication_tick(ts: pd.Timestamp) -> bool:
    """True at 13:00 Europe/Berlin — DA prices for tomorrow are already public."""
    t = as_berlin(ts)
    return t.hour == DA_PUBLICATION_HOUR_BERLIN and t.minute == 0


@dataclass
class SimClock:
    index: pd.DatetimeIndex
    speed: float = 0.0  # 0 = as-fast-as-possible
    _i: int = 0

    def __post_init__(self) -> None:
        if self.speed < 0:
            raise ValueError("speed must be >= 0")
        self.index = pd.DatetimeIndex(self.index)
        self._i = 0

    def __len__(self) -> int:
        return len(self.index)

    @property
    def done(self) -> bool:
        return self._i >= len(self.index)

    @property
    def now(self) -> pd.Timestamp:
        if self.done:
            return self.index[-1]
        return self.index[self._i]

    def step(self) -> pd.Timestamp | None:
        if self.done:
            return None
        ts = self.index[self._i]
        self._i += 1
        if self.speed > 0 and self._i < len(self.index):
            nxt = self.index[self._i]
            sim_s = (nxt - ts).total_seconds()
            if sim_s > 0:
                time.sleep(sim_s / self.speed)
        return ts
