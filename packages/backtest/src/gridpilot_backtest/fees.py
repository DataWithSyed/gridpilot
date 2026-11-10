"""Published market-fee catalog for the DE-LU paper-trading cost layer.

Retrieval date for every entry: 2026-11-10 (Asia/Karachi). Figures are copied
only from public documents opened that day. Missing current public figures are
flagged ``not_found`` or ``assumed`` — nothing is invented.

Paper trading only: this module never places or routes real orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Status = Literal["sourced", "assumed", "not_found", "not_applied", "historical", "derived_context"]

RETRIEVAL_DATE = "2026-11-10"

# Official published variable fees used in the sourced ExecutionCosts preset.
ECC_DA_CLEARING_EUR_PER_MWH = 0.015  # ECC Price List 085b, Power Day-ahead Spot (ECC Lux)
ECC_ID_CLEARING_EUR_PER_MWH = 0.035  # same list, Power Intraday Spot / IDAs (not used in DA-only runs)

# Still-assumed degradation inherited from A-C3 — no public €/MWh cycle-wear
# tariff was found (see catalog).
ASSUMED_DEGRADATION_EUR_PER_MWH = 5.0


@dataclass(frozen=True)
class FeeCitation:
    """One published (or explicitly missing) cost item."""

    id: str
    item: str
    status: Status
    value: str | float | None
    unit: str
    tariff_year: str | None
    retrieval_date: str
    source_title: str
    source_url: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FEE_CATALOG: tuple[FeeCitation, ...] = (
    FeeCitation(
        id="S-EPEX-DA-TRADING",
        item="EPEX SPOT Day-Ahead trading fee (DE-LU)",
        status="not_found",
        value=None,
        unit="EUR/MWh",
        tariff_year="2026",
        retrieval_date=RETRIEVAL_DATE,
        source_title="EPEX SPOT Fees page and New Price List Guide (public)",
        source_url="https://www.epexspot.com/en/fees",
        notes=(
            "The public Fees page and the downloadable Price List Guide describe Market Access, "
            "Flat Trading Fees, and Technical Add-ons qualitatively and direct readers to "
            "sales@epexspot.com. No current €/MWh or annual membership figure is printed in those "
            "public documents (retrieved 2026-11-10). The sourced per-MWh preset therefore does "
            "not include an EPEX trading-fee component. This is a lower bound on total exchange "
            "costs if a member still pays a trading fee. Guide PDF: "
            "https://www.epexspot.com/sites/default/files/download_center_files/New%20Price%20List%20Guide.pdf"
        ),
    ),
    FeeCitation(
        id="H-EPEX-2015",
        item="Historical EPEX SPOT trading fees (NOT used in the sourced preset)",
        status="historical",
        value="DA DE-AT-CH 0.04; FR DA 0.07; ID 0.10 (2015 list)",
        unit="EUR/MWh",
        tariff_year="2015",
        retrieval_date=RETRIEVAL_DATE,
        source_title="EPEX SPOT Price List valid 1 January 2015 (unofficial host; stale)",
        source_url="https://abcdocz.com/doc/668004/price-list---epex-spot",
        notes=(
            "Historical public list only, retrieved for context. Entrance 25,000 €; annual "
            "one/two/three market access 10,000 / 20,000 / 30,000 €; ETS Standard 8,000 € / "
            "Light 3,500 €. These are not current official rates and are not used in the sourced "
            "preset. They informed the earlier ASSUMED 0.05 €/MWh order-of-magnitude (A-C1)."
        ),
    ),
    FeeCitation(
        id="S-ECC-DA-CLEARING",
        item="ECC Lux clearing fee — Power Day-ahead Spot trades",
        status="sourced",
        value=0.015,
        unit="EUR/MWh",
        tariff_year="2026",
        retrieval_date=RETRIEVAL_DATE,
        source_title="ECC Price List, Document Release 085b, 02.11.2026, §4.1 Power spot",
        source_url=(
            "https://www.ecc.de/fileadmin/ECC/Downloads/About_ECC_AG/Rules/Price_List/"
            "Current_Price_List/20261102_ECC_Price_List_085b.pdf"
        ),
        notes=(
            "Official current price list (English information version; German legally binding), "
            "publishing date 2 November 2026, linked from https://www.ecc.de/en/rules-regulations/rules. "
            "Standard rate 0.015 €/MWh for Power Day-ahead Spot trades (ECC Lux). Exceptions "
            "(Serbia/Slovenia 0.020, Ireland, GB) do not apply to DE-LU. Baltic DA auction "
            "waiver is also not DE-LU. This is the only variable €/MWh figure in the sourced "
            "DA fee preset."
        ),
    ),
    FeeCitation(
        id="S-ECC-ID-CLEARING",
        item="ECC Lux clearing fee — Power Intraday Spot / SIDC IDAs",
        status="sourced",
        value=0.035,
        unit="EUR/MWh",
        tariff_year="2026",
        retrieval_date=RETRIEVAL_DATE,
        source_title="ECC Price List 085b, 02.11.2026, §4.1 Power spot",
        source_url=(
            "https://www.ecc.de/fileadmin/ECC/Downloads/About_ECC_AG/Rules/Price_List/"
            "Current_Price_List/20261102_ECC_Price_List_085b.pdf"
        ),
        notes=(
            "0.035 €/MWh for Power Intraday Spot trades; footnote *4 states the same rate "
            "applies to Pan-European Intraday Auctions (IDAs). Documented for completeness. "
            "The current paper model is day-ahead only, so this rate is not added to the sourced "
            "DA ExecutionCosts preset."
        ),
    ),
    FeeCitation(
        id="S-ECC-MEMBERSHIP",
        item="ECC membership fees (fixed, not converted to €/MWh)",
        status="sourced",
        value="NCM 1,000 € p.a.; Institution CM 12,500 € p.a.; DCP Power Markets Plus 12,500 € p.a.",
        unit="EUR/year",
        tariff_year="2026",
        retrieval_date=RETRIEVAL_DATE,
        source_title="ECC Price List 085b, 02.11.2026, §2 Membership Fees",
        source_url=(
            "https://www.ecc.de/fileadmin/ECC/Downloads/About_ECC_AG/Rules/Price_List/"
            "Current_Price_List/20261102_ECC_Price_List_085b.pdf"
        ),
        notes=(
            "Non-Clearing Member 1,000 € p.a. (clearing-fee credit against the membership fee; "
            "first 12 months waived). Institution Clearing Member 12,500 € p.a. (first 12 months "
            "waived). DCP Power Markets Plus 12,500 € p.a. (or 11,000 £ if GBP power only). "
            "Technical access EUREX GUI via public Internet 7,500 € p.a. (not applicable to DCP). "
            "Fixed fees are disclosed here and are not amortised into the per-MWh sourced preset: "
            "any €/MWh conversion would depend on annual throughput and membership type (modelling "
            "choice, not a published tariff)."
        ),
    ),
    FeeCitation(
        id="S-NORDPOOL-NORDIC-BALTIC",
        item="Nord Pool variable DA fees (Nordic/Baltic 2026 schedule; NEMO comparator, not EPEX DE-LU)",
        status="sourced",
        value="DA trading 0.040 + clearing 0.015 = 0.055",
        unit="EUR/MWh",
        tariff_year="2026",
        retrieval_date=RETRIEVAL_DATE,
        source_title="Nord Pool AS Fee Schedule, Nordic / Baltic Market, effective 1 January 2026",
        source_url=(
            "https://www.nordpoolgroup.com/4a7ad8/globalassets/trading-and-services/"
            "nord-pool-fee-schedule-2026-nordic-and-baltic-market.pdf"
        ),
        notes=(
            "Official PDF retrieved 2026-11-10. Section 1.4: Day-ahead market trading 0.040 €/MWh "
            "and clearing 0.015 €/MWh (combined 0.055); small participant DA 0.125+0.015=0.140; "
            "intraday continuous 0.109+0.015=0.124; SIDC IDA 0.060+0.015=0.075. Annual participant "
            "access DA+ID continuous: 21,500 € (additional area 11,000 €); small participant can "
            "waive the annual fee and pay the higher variable rate (floors apply). Note (b) lists "
            "Germany/Luxembourg among the areas used for the 65,000 € annual access-fee cap when "
            "applying for multiple Nord Pool areas. The document title is 'Nordic / Baltic Market'; "
            "a separate public CWE/DE-LU fee schedule was not found at retrieval. These rates are "
            "a published NEMO comparator, not a substitute for the unpublished current EPEX DE-LU "
            "trading fee, and they are not added to the sourced ExecutionCosts preset."
        ),
    ),
    FeeCitation(
        id="S-ENWG-118-6",
        item="German grid-access charges (Netzentgelte) for eligible electricity storage",
        status="sourced",
        value=0.0,
        unit="EUR/MWh",
        tariff_year="2026 (statutory)",
        retrieval_date=RETRIEVAL_DATE,
        source_title="Energiewirtschaftsgesetz (EnWG) § 118(6), gesetze-im-internet.de",
        source_url="https://www.gesetze-im-internet.de/enwg_2005/__118.html",
        notes=(
            "Official text: installations for storing electrical energy newly built after "
            "31 December 2008 and commissioned from 4 August 2011 within 18 years (i.e. by "
            "4 August 2029) are exempt for 20 years from commissioning from grid-access charges "
            "(Entgelte für den Netzzugang) on energy withdrawn for storage, provided the energy "
            "is taken from a transmission or distribution grid and the recovered energy is fed "
            "back into the same grid. The exemption does not automatically cover every levy or "
            "concession fee. For the illustrative 1 MW / 2 MWh paper asset, assumed commissioned "
            "in the exemption window and same-grid, the sourced preset applies 0 €/MWh grid-access "
            "charge on stored energy. This is a legal condition, not a published TSO tariff table."
        ),
    ),
    FeeCitation(
        id="S-REBAP",
        item="German imbalance settlement price (reBAP)",
        status="not_applied",
        value=None,
        unit="EUR/MWh (quarter-hourly, published, not a fixed tariff)",
        tariff_year="2026",
        retrieval_date=RETRIEVAL_DATE,
        source_title="Netztransparenz — Ausgleichsenergiepreis / reBAP (four German TSOs)",
        source_url="https://www.netztransparenz.de/de-de/Regelenergie/Ausgleichsenergiepreis",
        notes=(
            "reBAP is a published quarter-hourly settlement price for balance-group imbalances, "
            "not a fixed €/MWh trading fee. It can be positive or negative. The current paper "
            "model is day-ahead only and settles planned DA volumes at the DA clearing price, "
            "so no imbalance volume is simulated and no reBAP charge is applied. A live physical "
            "asset would face reBAP on residual imbalances."
        ),
    ),
    FeeCitation(
        id="S-DA-SLIPPAGE",
        item="Day-ahead slippage / bid-ask (SDAC single clearing price)",
        status="sourced",
        value=0.0,
        unit="EUR/MWh",
        tariff_year="2026",
        retrieval_date=RETRIEVAL_DATE,
        source_title="Market design: SDAC day-ahead auction (single clearing price per MTU)",
        source_url="https://www.epexspot.com/en/downloads",
        notes=(
            "The coupled day-ahead auction produces one clearing price per market time unit. "
            "There is no classic bid-ask spread on a filled DA auction trade. The sourced DA "
            "preset therefore sets slippage to 0 (pure auction-fill paper assumption). The "
            "previous 0.50 €/MWh figure remains an ASSUMED conservatism (A-C2) in the assumed "
            "preset, not a published fee."
        ),
    ),
    FeeCitation(
        id="A-DEGRADATION",
        item="Battery degradation €/MWh throughput",
        status="assumed",
        value=5.0,
        unit="EUR/MWh throughput",
        tariff_year=None,
        retrieval_date=RETRIEVAL_DATE,
        source_title=(
            "NREL/NLR 2025 Annual Technology Baseline — Utility-Scale Battery Storage "
            "(context only; no published €/MWh wear tariff)"
        ),
        source_url="https://atb.nlr.gov/electricity/2025/utility-scale_battery_storage",
        notes=(
            "No public exchange or TSO document publishes a battery degradation tariff in €/MWh. "
            "NREL/NLR ATB 2025 (LFP utility-scale, retrieved 2026-11-10) states a 15-year technical "
            "life, approximately one cycle per day, variable O&M of zero, and fixed O&M at 4% of "
            "capital cost in $/kW including augmentation so the system can hold rated capacity over "
            "that life (Cole et al., 2025). A primary-source 2024 overnight $/kWh table was not "
            "successfully retrieved this day (NREL PDF TLS failure), so no €/MWh figure is derived "
            "here. The sourced preset therefore keeps the existing ASSUMED 5 €/MWh throughput "
            "wear proxy (A-C3; Kies et al. 2018 DOI 10.1088/1742-6596/977/1/012005 is order-of-magnitude "
            "framing only)."
        ),
    ),
)


def catalog_dicts() -> list[dict[str, Any]]:
    return [c.to_dict() for c in FEE_CATALOG]


def citations_by_status(*status: Status) -> tuple[FeeCitation, ...]:
    return tuple(c for c in FEE_CATALOG if c.status in status)


def sourced_preset_components() -> dict[str, Any]:
    """Breakdown of the 'sourced' ExecutionCosts preset — honest about gaps."""
    return {
        "label": "sourced",
        "retrieval_date": RETRIEVAL_DATE,
        "fee_eur_per_mwh": ECC_DA_CLEARING_EUR_PER_MWH,
        "fee_composition": {
            "ecc_da_clearing_eur_per_mwh": ECC_DA_CLEARING_EUR_PER_MWH,
            "epex_trading_eur_per_mwh": None,
            "epex_trading_status": "not_found_in_current_public_price_list",
        },
        "slippage_eur_per_mwh": 0.0,
        "slippage_status": "sourced",
        "degradation_eur_per_mwh": ASSUMED_DEGRADATION_EUR_PER_MWH,
        "degradation_status": "assumed",
        "grid_access_eur_per_mwh": 0.0,
        "grid_access_status": "sourced_enwg_118_6_if_eligible",
        "imbalance": "not_applied_da_only_paper_model",
        "fixed_membership_fees": "disclosed_in_catalog_not_amortised_into_per_mwh",
        "still_assumed": ["degradation_eur_per_mwh"],
        "not_in_preset": [
            "current EPEX SPOT trading fee (not in the public 2026 Price List Guide)",
            "ECC / EPEX annual membership and technical fees (fixed; not converted to €/MWh)",
            "ECC intraday clearing 0.035 €/MWh (DA-only model)",
            "Nord Pool Nordic/Baltic variable fees (comparator only)",
            "reBAP imbalance (not a fixed tariff; no imbalance volume in this model)",
        ],
        "paper_trading_only": True,
        "is_lower_bound_on_exchange_fees": True,
        "catalog": catalog_dicts(),
    }
