import pandas as pd
import pytest

from gridpilot_data.schema import TZ, validate_power_frame, validate_price_frame


def test_validate_price_ok():
    idx = pd.date_range("2026-08-01", periods=3, freq="h", tz=TZ)
    df = pd.DataFrame({"da_price_eur_mwh": [10.0, 20.0, 30.0]}, index=idx)
    out = validate_price_frame(df)
    assert list(out.columns) == ["da_price_eur_mwh"]


def test_validate_price_missing_col():
    idx = pd.date_range("2026-08-01", periods=2, freq="h", tz=TZ)
    df = pd.DataFrame({"x": [1.0, 2.0]}, index=idx)
    with pytest.raises(ValueError, match="missing"):
        validate_price_frame(df)


def test_validate_power_needs_one_col():
    idx = pd.date_range("2026-08-01", periods=2, freq="h", tz=TZ)
    df = pd.DataFrame({"other": [1.0, 2.0]}, index=idx)
    with pytest.raises(ValueError, match="at least one"):
        validate_power_frame(df)
