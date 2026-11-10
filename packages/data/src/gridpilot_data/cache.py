"""Simple JSON/Parquet disk cache for adapter payloads."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"


def ensure_dir(path: Path | None = None) -> Path:
    d = Path(path) if path is not None else DEFAULT_CACHE
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
