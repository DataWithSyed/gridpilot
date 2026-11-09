"""Append-only event log for paper-trading decisions and fills."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd

EventKind = Literal[
    "bar",
    "decision",
    "fill",
    "risk_block",
    "kill_switch",
    "day_end",
    "info",
]


@dataclass
class Event:
    ts: Any
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)


class EventLog:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def emit(self, ts: Any, kind: EventKind, **payload: Any) -> None:
        self._events.append(Event(ts=ts, kind=kind, payload=payload))

    def __len__(self) -> int:
        return len(self._events)

    def to_frame(self) -> pd.DataFrame:
        if not self._events:
            return pd.DataFrame(columns=["ts", "kind"])
        rows = []
        for e in self._events:
            row = {"ts": e.ts, "kind": e.kind}
            row.update(e.payload)
            rows.append(row)
        return pd.DataFrame(rows)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self._events]
