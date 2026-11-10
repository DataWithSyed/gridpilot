"""Sourced fee catalog and cost preset — no invented current EPEX rates."""
from __future__ import annotations

import pytest

from gridpilot_backtest.costs import (
    ASSUMED_BASE_COSTS,
    SOURCED_COSTS,
    apply_costs_to_actions,
    get_cost_preset,
)
from gridpilot_backtest.fees import (
    ECC_DA_CLEARING_EUR_PER_MWH,
    ECC_ID_CLEARING_EUR_PER_MWH,
    FEE_CATALOG,
    RETRIEVAL_DATE,
    sourced_preset_components,
)


def test_retrieval_date_is_explicit():
    assert RETRIEVAL_DATE == "2026-11-10"
    for item in FEE_CATALOG:
        assert item.retrieval_date == RETRIEVAL_DATE
        assert item.source_url.startswith("http")
        assert item.status in {
            "sourced",
            "assumed",
            "not_found",
            "not_applied",
            "historical",
            "derived_context",
        }
        assert item.item
        assert item.notes


def test_sourced_preset_uses_ecc_clearing_only():
    costs = get_cost_preset("sourced")
    assert costs is SOURCED_COSTS
    assert costs.fee_eur_per_mwh == pytest.approx(ECC_DA_CLEARING_EUR_PER_MWH)
    assert costs.fee_eur_per_mwh == pytest.approx(0.015)
    assert costs.slippage_eur_per_mwh == 0.0
    assert costs.degradation_eur_per_mwh == pytest.approx(5.0)
    assert costs.label == "sourced"
    payload = costs.to_dict()
    assert payload["cost_basis"] == "sourced"
    assert payload["assumed"] is False
    assert "degradation_eur_per_mwh" in payload["still_assumed"]
    assert payload["fee_composition"]["epex_trading_eur_per_mwh"] is None
    assert payload["is_lower_bound_on_exchange_fees"] is True


def test_no_invented_current_epex_trading_fee():
    epex = next(c for c in FEE_CATALOG if c.id == "S-EPEX-DA-TRADING")
    assert epex.status == "not_found"
    assert epex.value is None
    # Historical 2015 list must not leak into the sourced per-MWh fee.
    hist = next(c for c in FEE_CATALOG if c.id == "H-EPEX-2015")
    assert hist.status == "historical"
    assert SOURCED_COSTS.fee_eur_per_mwh != 0.04
    assert SOURCED_COSTS.fee_eur_per_mwh != 0.05


def test_ecc_and_nordpool_and_enwg_are_sourced():
    by_id = {c.id: c for c in FEE_CATALOG}
    assert by_id["S-ECC-DA-CLEARING"].value == 0.015
    assert by_id["S-ECC-ID-CLEARING"].value == ECC_ID_CLEARING_EUR_PER_MWH
    assert by_id["S-ECC-MEMBERSHIP"].status == "sourced"
    assert by_id["S-NORDPOOL-NORDIC-BALTIC"].status == "sourced"
    assert by_id["S-ENWG-118-6"].value == 0.0
    assert by_id["S-REBAP"].status == "not_applied"
    assert by_id["A-DEGRADATION"].status == "assumed"
    assert by_id["S-DA-SLIPPAGE"].value == 0.0


def test_assumed_preset_unchanged():
    assert get_cost_preset("assumed") is ASSUMED_BASE_COSTS
    assert get_cost_preset("base") is ASSUMED_BASE_COSTS
    assert ASSUMED_BASE_COSTS.fee_eur_per_mwh == pytest.approx(0.05)
    assert ASSUMED_BASE_COSTS.slippage_eur_per_mwh == pytest.approx(0.50)
    assert ASSUMED_BASE_COSTS.degradation_eur_per_mwh == pytest.approx(5.0)
    with pytest.raises(ValueError, match="Unknown cost preset"):
        get_cost_preset("made-up")


def test_sourced_costs_less_punitive_than_assumed_on_same_fills():
    import numpy as np
    import pandas as pd

    idx = pd.date_range("2026-01-01", periods=24, freq="h", tz="Europe/Berlin")
    acts = pd.DataFrame(
        {
            "ts": idx,
            "price": np.linspace(40, 160, 24),
            "grid_in_mwh": [1.0 if i % 4 == 0 else 0.0 for i in range(24)],
            "grid_out_mwh": [1.0 if i % 4 == 2 else 0.0 for i in range(24)],
        }
    )
    assumed = apply_costs_to_actions(acts, ASSUMED_BASE_COSTS)["final_cash_eur"]
    sourced = apply_costs_to_actions(acts, SOURCED_COSTS)["final_cash_eur"]
    assert sourced > assumed


def test_sourced_preset_components_are_honest():
    comp = sourced_preset_components()
    assert comp["is_lower_bound_on_exchange_fees"] is True
    assert "degradation_eur_per_mwh" in comp["still_assumed"]
    assert comp["paper_trading_only"] is True
    assert comp["fee_composition"]["epex_trading_eur_per_mwh"] is None
