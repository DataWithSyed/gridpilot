"""Add in-repo package src/ dirs to sys.path (single-repo layout)."""
from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_SRC = (
    "packages/core/src",
    "packages/data/src",
    "packages/risk/src",
    "packages/strategies/src",
    "packages/forecast/src",
    "packages/backtest/src",
    "packages/live/src",
    "packages/dashboard/src",
)

CACHE_CANDIDATES = (
    "packages/forecast/data/cache",
    "packages/data/data/cache",
    "packages/core/data/cache",
)


def umbrella_root(start: Path | None = None) -> Path:
    p = (start or Path(__file__)).resolve()
    if p.is_file():
        p = p.parent
    for cand in (p, *p.parents):
        if (cand / "packages" / "core" / "src").exists() and (cand / "README.md").exists():
            return cand
    # packages/_srcpaths.py lives one level below the repo root
    return Path(__file__).resolve().parents[1]


def add_src_paths(umbrella: Path | None = None) -> Path:
    root = umbrella or umbrella_root()
    for rel in PACKAGE_SRC:
        d = root / rel
        if d.exists() and str(d) not in sys.path:
            sys.path.insert(0, str(d))
    return root


def default_cache(umbrella: Path | None = None) -> Path:
    root = umbrella or umbrella_root()
    for rel in CACHE_CANDIDATES:
        d = root / rel
        if d.exists() and any(d.glob("*.csv*")):
            return d
    return root / "packages/forecast/data/cache"
