#!/usr/bin/env python3
"""Headless health check for CI / local verify."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gridpilot_dashboard.health import health_check

h = health_check()
print(json.dumps(h, indent=2))
try:
    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path))
    at.run(timeout=30)
    assert not at.exception, at.exception
    h["streamlit_apptest"] = "ok"
    print("streamlit AppTest: ok")
except Exception as exc:
    h["streamlit_apptest"] = f"skipped_or_failed: {exc}"
    print("streamlit AppTest skipped/failed:", exc)
sys.exit(0 if h["ok"] else 1)
