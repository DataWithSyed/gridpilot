#!/usr/bin/env python3
"""Run the near-live paper pilot (no real orders)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UMBRELLA = ROOT.parents[1]
GP = UMBRELLA.parent
for p in (
    ROOT / "src",
    UMBRELLA / "packages" / "forecast" / "src",
    GP / "gridpilot-core" / "src",
    GP / "gridpilot-strategies" / "src",
    GP / "gridpilot-data" / "src",
):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gridpilot_live.cli import main

if __name__ == "__main__":
    main()
