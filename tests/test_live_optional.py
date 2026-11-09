import os
from pathlib import Path

import pytest

from gridpilot_data.adapters import EnergyChartsAdapter

pytestmark = pytest.mark.skipif(
    os.environ.get("GRIDPILOT_SKIP_LIVE", "1") == "1",
    reason="Set GRIDPILOT_SKIP_LIVE=0 to hit Energy-Charts live",
)


def test_live_price_fetch(tmp_path):
    ad = EnergyChartsAdapter(cache_dir=tmp_path)
    s = ad.fetch_day_ahead_prices("2026-08-01", "2026-08-02")
    assert len(s) >= 24
    assert s.notna().any()
