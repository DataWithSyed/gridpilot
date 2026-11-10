import os

import pytest

from gridpilot_core.data_replay import fetch_day_ahead_prices


@pytest.mark.skipif(os.environ.get("GRIDPILOT_SKIP_LIVE") == "1", reason="live fetch skipped")
def test_live_short_window_fetch_hourly(tmp_path):
    s = fetch_day_ahead_prices(
        "2026-09-01", "2026-09-02", cache_dir=tmp_path, refresh=True, to_hourly=True
    )
    assert len(s) >= 24
    assert s.notna().all()
    assert s.min() > -500
    assert s.max() < 5000


@pytest.mark.skipif(os.environ.get("GRIDPILOT_SKIP_LIVE") == "1", reason="live fetch skipped")
def test_live_native_quarter_hour(tmp_path):
    s = fetch_day_ahead_prices(
        "2026-09-01", "2026-09-01", cache_dir=tmp_path, refresh=False, to_hourly=False
    )
    # One calendar day of 15-min MTUs
    assert len(s) >= 90
