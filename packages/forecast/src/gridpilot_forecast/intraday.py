"""Post day-ahead re-optimisation and imbalance cash-out (paper trading only).

Energy-Charts (Fraunhofer ISE) was checked on 2026-11-10: the public API
exposes only day-ahead prices (``/price``, ``/v2/price``). There is no
intraday or ID-index endpoint; ``?market=intraday`` is ignored and returns
identical DA values. This module therefore uses a clearly labelled proxy:

    PROXY_ID_EQ_DA — ID mid equals the realised DA clearing price.

That measures the value of reshaping the schedule after DA prices are
published (~12:45 Europe/Berlin on D-1), assuming ID trades occur at DA
(no ID–DA spread). True ID value can be higher or lower when the ID
index diverges from DA. ECC ID clearing 0.035 €/MWh is applied to ID
volume (sourced; EPEX ID trading fee still unpublished).

Netztransparenz reBAP (quarter-hourly Ausgleichsenergiepreis) is published,
but the data API (docs v1.14, 7 Feb 2025) requires OAuth 2.0 client
credentials issued via the Netztransparenz Extranet. Unauthenticated
calls to ``https://ds.netztransparenz.de/api/v1/data/NrvSaldo/reBAP/Qualitaetsgesichert``
return 404; the public HTML page has no bulk CSV. This module therefore
uses a clearly labelled proxy unless a local reBAP series is supplied:

    PROXY_REBAP_EQ_DA — imbalance is cashed out at the realised DA price.

That ignores reBAP scarcity adders (AEP modules) and is not official reBAP.
A leftover fraction of the intended ID volume can be left as imbalance
(``unfilled_frac``, ASSUMED).

Never places real orders.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from gridpilot_backtest.costs import ExecutionCosts, SOURCED_COSTS
from gridpilot_backtest.fees import ECC_ID_CLEARING_EUR_PER_MWH
from gridpilot_core.battery import BatteryConfig, BatteryState
from gridpilot_core.strategy import Decision
from gridpilot_forecast.bid_curves import settle_locked_schedule
from gridpilot_forecast.cost_aware_lp import solve_day_lp_with_costs

ID_PRICE_SOURCE = "proxy_id_eq_da"
REBAP_SOURCE = "proxy_rebap_eq_da"
ID_PRICE_SOURCE_NOTES = (
    "Energy-Charts public API has no intraday or ID-index series "
    "(verified 2026-11-10: only /price day-ahead; market=intraday is ignored). "
    "ID mid is proxied by the realised DA clearing price."
)
REBAP_SOURCE_NOTES = (
    "Netztransparenz reBAP API requires Extranet OAuth client credentials "
    "(docs v1.14, 2025-02-07); unauthenticated data URLs returned 404. "
    "Imbalance is cashed out at the realised DA price unless a local series is provided."
)

SOURCED_ID_COSTS = ExecutionCosts(
    fee_eur_per_mwh=ECC_ID_CLEARING_EUR_PER_MWH,
    slippage_eur_per_mwh=0.0,
    degradation_eur_per_mwh=SOURCED_COSTS.degradation_eur_per_mwh,
    label="sourced_id_proxy",
)


@dataclass(frozen=True)
class IntradayLayerConfig:
    """Paper ID / imbalance layer on top of a locked DA schedule."""

    da_costs: ExecutionCosts = SOURCED_COSTS
    id_costs: ExecutionCosts = SOURCED_ID_COSTS
    unfilled_frac: float = 0.0  # ASSUMED share of intended ID volume left as imbalance
    id_price_source: str = ID_PRICE_SOURCE
    rebap_source: str = REBAP_SOURCE

    def __post_init__(self) -> None:
        if not (0.0 <= float(self.unfilled_frac) <= 1.0):
            raise ValueError("unfilled_frac must be in [0, 1]")


def _col(df: pd.DataFrame, name: str, ts: pd.Timestamp) -> float:
    row = df.loc[df["ts"] == ts]
    if row.empty:
        return 0.0
    return float(row[name].iloc[0])


def _energy_cash(
    gin: float,
    gout: float,
    price: float,
    costs: ExecutionCosts,
    *,
    fee: bool,
    deg: bool,
) -> float:
    buy = price + costs.slippage_eur_per_mwh
    sell = price - costs.slippage_eur_per_mwh
    cash = -gin * buy + gout * sell
    thr = gin + gout
    if fee:
        cash -= thr * costs.fee_eur_per_mwh
    if deg:
        cash -= thr * costs.degradation_eur_per_mwh
    return float(cash)


def _id_legs(gin_da: float, gout_da: float, gin_ph: float, gout_ph: float) -> tuple[float, float]:
    """ID buy/sell volume that walks the DA nomination to the physical plan."""
    id_buy = 0.0
    id_sell = 0.0
    if gin_ph >= gin_da:
        id_buy += gin_ph - gin_da
    else:
        id_sell += gin_da - gin_ph
    if gout_ph >= gout_da:
        id_sell += gout_ph - gout_da
    else:
        id_buy += gout_da - gout_ph
    return id_buy, id_sell


def reoptimize_after_da(
    da_plan: dict[pd.Timestamp, Decision],
    da_prices: pd.Series,
    battery: BatteryConfig,
    soc: float,
    cfg: IntradayLayerConfig,
    *,
    dt_h: float = 1.0,
    id_prices: pd.Series | None = None,
    rebap: pd.Series | None = None,
) -> dict:
    """Re-solve the delivery day after DA prices are published and settle the stack.

    ``id_prices`` and ``rebap`` default to the DA series (labelled proxies).
    Physical dispatch follows the re-optimised plan. Intended ID volume is
    the walk from the DA nomination to that plan; a fraction
    ``unfilled_frac`` is cashed out at reBAP instead of the ID proxy.
    Degradation is charged once, on physical throughput. Paper only.
    """
    prices = da_prices.astype(float)
    id_px = (id_prices if id_prices is not None else prices).astype(float).reindex(prices.index)
    id_px = id_px.fillna(prices)
    rb = (rebap if rebap is not None else prices).astype(float).reindex(prices.index)
    rb = rb.fillna(prices)

    da_acts = settle_locked_schedule(da_plan, prices, battery, soc, dt_h=dt_h, note="da_nomination")
    phys_plan = solve_day_lp_with_costs(
        id_px,
        battery,
        BatteryState(soc=soc),
        cfg.id_costs,
        dt_h=dt_h,
        note="id_reopt",
    )
    phys_acts = settle_locked_schedule(phys_plan, prices, battery, soc, dt_h=dt_h, note="id_physical")

    u = float(cfg.unfilled_frac)
    rows = []
    cash = 0.0
    for ts, da_p in prices.items():
        gin_da = _col(da_acts, "grid_in_mwh", ts)
        gout_da = _col(da_acts, "grid_out_mwh", ts)
        gin_ph = _col(phys_acts, "grid_in_mwh", ts)
        gout_ph = _col(phys_acts, "grid_out_mwh", ts)
        id_buy, id_sell = _id_legs(gin_da, gout_da, gin_ph, gout_ph)
        id_in = (1.0 - u) * id_buy
        id_out = (1.0 - u) * id_sell
        ip = float(id_px.loc[ts])
        rp = float(rb.loc[ts])
        nom_net = (gout_da + id_out) - (gin_da + id_in)
        phys_net = gout_ph - gin_ph
        imb_net = phys_net - nom_net
        step = (
            _energy_cash(gin_da, gout_da, float(da_p), cfg.da_costs, fee=True, deg=False)
            + _energy_cash(id_in, id_out, ip, cfg.id_costs, fee=True, deg=False)
            + imb_net * rp
            - (gin_ph + gout_ph) * cfg.da_costs.degradation_eur_per_mwh
        )
        cash += step
        rows.append(
            {
                "ts": ts,
                "price": float(da_p),
                "id_price": ip,
                "rebap": rp,
                "grid_in_mwh": gin_ph,
                "grid_out_mwh": gout_ph,
                "da_in_mwh": gin_da,
                "da_out_mwh": gout_da,
                "id_in_mwh": id_in,
                "id_out_mwh": id_out,
                "imb_net_mwh": imb_net,
                "cash": cash,
                "soc": _col(phys_acts, "soc", ts),
                "note": "id_reopt" + ("|partial_id" if u > 0 else ""),
            }
        )
    actions = pd.DataFrame(rows)
    return {
        "actions": actions,
        "da_actions": da_acts,
        "physical_actions": phys_acts,
        "final_cash_eur": float(cash),
        "id_throughput_mwh": float(actions["id_in_mwh"].sum() + actions["id_out_mwh"].sum()) if len(actions) else 0.0,
        "imb_abs_mwh": float(actions["imb_net_mwh"].abs().sum()) if len(actions) else 0.0,
        "end_soc": float(actions["soc"].iloc[-1]) if len(actions) else float(soc),
        "id_price_source": cfg.id_price_source if id_prices is None else "provided_series",
        "rebap_source": cfg.rebap_source if rebap is None else "provided_series",
        "unfilled_frac": u,
    }
