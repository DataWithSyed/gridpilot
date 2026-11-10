import json
from pathlib import Path

import pandas as pd
import pytest

from gridpilot_data.adapters import EnergyChartsAdapter, EntsoeAdapter, ReplayAdapter
from gridpilot_data.schema import TZ


def test_replay_adapter_slices(tmp_path):
    idx = pd.date_range("2026-08-01", periods=48, freq="h", tz=TZ)
    s = pd.Series(range(48), index=idx, dtype=float, name="da_price_eur_mwh")
    path = tmp_path / "prices.csv"
    s.to_csv(path, header=True)
    ad = ReplayAdapter(path)
    out = ad.fetch_day_ahead_prices("2026-08-01", "2026-08-01")
    assert len(out) == 24
    assert out.index.tz is not None
    assert out.name == "da_price_eur_mwh"


def test_replay_from_series():
    idx = pd.date_range("2026-08-01", periods=24, freq="h", tz=TZ)
    s = pd.Series(100.0, index=idx)
    ad = ReplayAdapter(s)
    out = ad.fetch_day_ahead_prices("2026-08-01", "2026-08-01")
    assert len(out) == 24
    assert float(out.mean()) == 100.0


def test_entsoe_requires_env(monkeypatch):
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ENTSOE_API_TOKEN"):
        EntsoeAdapter()


def test_energy_charts_uses_cache(tmp_path):
    # Minimal synthetic Energy-Charts v2 payload
    payload = {
        "license": "CC BY 4.0",
        "data": [
            {
                "timestamp": "2026-08-01T00:00:00+02:00",
                "values": {"day_ahead_price": 50.0},
            },
            {
                "timestamp": "2026-08-01T01:00:00+02:00",
                "values": {"day_ahead_price": 60.0},
            },
        ],
    }
    cache = tmp_path / "cache"
    cache.mkdir()
    # Match chunk filename pattern used by energy_charts.fetch_day_ahead_prices
    dest = cache / "ec_v2_price_DE-LU_20260801_20260801.json"
    dest.write_text(json.dumps(payload), encoding="utf-8")
    ad = EnergyChartsAdapter(cache_dir=cache)
    out = ad.fetch_day_ahead_prices("2026-08-01", "2026-08-01", refresh=False)
    assert len(out) == 2
    assert float(out.iloc[0]) == 50.0


def test_energy_charts_rejects_non_cc_by(tmp_path):
    payload = {
        "license": "All rights reserved",
        "data": [
            {
                "timestamp": "2026-08-01T00:00:00+02:00",
                "values": {"day_ahead_price": 1.0},
            }
        ],
    }
    cache = tmp_path / "cache"
    cache.mkdir()
    dest = cache / "ec_v2_price_DE-LU_20260801_20260801.json"
    dest.write_text(json.dumps(payload), encoding="utf-8")
    ad = EnergyChartsAdapter(cache_dir=cache)
    with pytest.raises(RuntimeError, match="CC BY"):
        ad.fetch_day_ahead_prices("2026-08-01", "2026-08-01", refresh=False)
