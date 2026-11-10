#!/usr/bin/env python3
"""Run the near-live paper pilot (no real orders)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UMBRELLA = ROOT.parents[1]
GP = UMBRELLA  # in-repo packages/ (legacy name kept for cache fallbacks)
import sys as _sys
_sys.path.insert(0, str(UMBRELLA / "packages"))
from _srcpaths import add_src_paths, default_cache
add_src_paths(UMBRELLA)

from gridpilot_live.cli import main

if __name__ == "__main__":
    main()
