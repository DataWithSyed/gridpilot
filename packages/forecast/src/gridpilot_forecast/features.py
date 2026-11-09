"""Price-lag + calendar + optional day-ahead fundamentals (ex-ante / causal).

Ex-ante rule (SDAC day-ahead, gate closure ~12:00 CET on D-1): for delivery day D
we may use prices through D-1 and TSO day-ahead load/solar/wind forecasts for day D.
Same-day realised prices or same-day actual generation must never enter features.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

TZ = "Europe/Berlin"


def easter_sunday(year: int) -> dt.date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def german_national_holidays(year: int) -> set[dt.date]:
    e = easter_sunday(year)
    fixed = [(1, 1), (5, 1), (10, 3), (12, 25), (12, 26)]
    out = {dt.date(year, m, d) for m, d in fixed}
    out |= {
        e - dt.timedelta(days=2),
        e + dt.timedelta(days=1),
        e + dt.timedelta(days=39),
        e + dt.timedelta(days=50),
    }
    return out


def to_berlin(prices: pd.Series) -> pd.Series:
    s = prices.dropna().astype(float).sort_index()
    if s.index.tz is None:
        s.index = s.index.tz_localize(TZ, ambiguous="infer", nonexistent="shift_forward")
    else:
        s.index = s.index.tz_convert(TZ)
    return s


def daily_panel(prices: pd.Series) -> pd.DataFrame:
    """Local-date x hour (0..23) mean prices. DST: mean of duplicate hours."""
    s = to_berlin(prices)
    df = pd.DataFrame({"date": s.index.date, "hour": s.index.hour, "p": s.to_numpy()})
    pan = df.pivot_table(index="date", columns="hour", values="p", aggfunc="mean")
    pan = pan.reindex(columns=range(24))
    pan.index = pd.to_datetime(pan.index)
    return pan


def calendar_row(day: pd.Timestamp) -> dict[str, float]:
    hol = german_national_holidays(day.year)
    return {
        "dow": float(day.day_of_week),
        "month": float(day.month),
        "holiday": 1.0 if day.date() in hol else 0.0,
    }


def lear_row(panel: pd.DataFrame, day: pd.Timestamp) -> np.ndarray | None:
    """Wide LEAR-lite features for delivery day ``day`` using only D-1/D-2/D-7 prices + calendar.

    Returns length ~79 vector or None if lags missing.
    """
    day = pd.Timestamp(day).normalize()
    parts: list[np.ndarray] = []
    for lag in (1, 2, 7):
        prev = day - pd.Timedelta(days=lag)
        if prev not in panel.index or panel.loc[prev].isna().any():
            return None
        parts.append(panel.loc[prev].to_numpy(float))
    d1 = panel.loc[day - pd.Timedelta(days=1)].to_numpy(float)
    parts.append(np.array([d1.mean(), d1.min(), d1.max()], dtype=float))
    cal = calendar_row(day)
    dow = np.zeros(7, dtype=float)
    dow[int(cal["dow"])] = 1.0
    parts.append(dow)
    parts.append(np.array([cal["month"], cal["holiday"]], dtype=float))
    return np.concatenate(parts)


def lear_row_with_fundamentals(
    price_panel: pd.DataFrame,
    fund: dict[str, pd.DataFrame],
    day: pd.Timestamp,
) -> np.ndarray | None:
    """LEAR-lite + day-ahead residual-load / renewables summaries for day D (ex-ante)."""
    base = lear_row(price_panel, day)
    if base is None:
        return None
    day = pd.Timestamp(day).normalize()
    rl = fund.get("residual_load_fc")
    load = fund.get("load_fc")
    wind = fund.get("wind_fc")
    solar = fund.get("solar_fc")
    extras: list[float] = []
    for pan, label in ((rl, "rl"), (load, "load"), (wind, "wind"), (solar, "solar")):
        if pan is None or day not in pan.index or pan.loc[day].isna().any():
            return None
        row = pan.loc[day].to_numpy(float)
        extras.extend([float(row.mean()), float(row.min()), float(row.max()), float(row[12]), float(row[19])])
        # D-1 profile of same series (already known)
        prev = day - pd.Timedelta(days=1)
        if prev in pan.index and not pan.loc[prev].isna().any():
            extras.append(float(pan.loc[prev].mean()))
        else:
            extras.append(float(row.mean()))
    return np.concatenate([base, np.asarray(extras, float)])


def gbm_frame_for_day(panel: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame | None:
    """Long 24-row feature table for QuantileGBM for delivery day ``day`` (price-only, ex-ante)."""
    day = pd.Timestamp(day).normalize()
    rows = []
    cal = calendar_row(day)
    try:
        p1 = panel.loc[day - pd.Timedelta(days=1)]
        p2 = panel.loc[day - pd.Timedelta(days=2)]
        p7 = panel.loc[day - pd.Timedelta(days=7)]
    except KeyError:
        return None
    if p1.isna().any() or p2.isna().any() or p7.isna().any():
        return None
    window_days = [day - pd.Timedelta(days=i) for i in range(1, 8)]
    means = []
    for d in window_days:
        if d in panel.index and not panel.loc[d].isna().all():
            means.append(float(panel.loc[d].mean()))
    p7d = float(np.mean(means)) if means else float(p1.mean())
    for h in range(24):
        rows.append(
            {
                "hour": h,
                "dow": int(cal["dow"]),
                "month": int(cal["month"]),
                "holiday": int(cal["holiday"]),
                "p_d1": float(p1.iloc[h]),
                "p_d2": float(p2.iloc[h]),
                "p_d7": float(p7.iloc[h]),
                "p_d1_mean": float(p1.mean()),
                "p_d1_min": float(p1.min()),
                "p_d1_max": float(p1.max()),
                "p_d1_h12": float(p1.iloc[12]),
                "p_d1_h19": float(p1.iloc[19]),
                "p_7d_mean": p7d,
            }
        )
    return pd.DataFrame(rows)


def gbm_frame_for_day_with_fundamentals(
    price_panel: pd.DataFrame,
    fund: dict[str, pd.DataFrame],
    day: pd.Timestamp,
) -> pd.DataFrame | None:
    """GBM long frame with day-ahead residual load / renewables (ex-ante for day D)."""
    base = gbm_frame_for_day(price_panel, day)
    if base is None:
        return None
    day = pd.Timestamp(day).normalize()
    rl = fund.get("residual_load_fc")
    load = fund.get("load_fc")
    wind = fund.get("wind_fc")
    solar = fund.get("solar_fc")
    for pan in (rl, load, wind, solar):
        if pan is None or day not in pan.index or pan.loc[day].isna().any():
            return None
    rl_d = rl.loc[day]
    load_d = load.loc[day]
    wind_d = wind.loc[day]
    solar_d = solar.loc[day]
    prev = day - pd.Timedelta(days=1)
    rl_d1 = rl.loc[prev] if prev in rl.index else rl_d
    rows = []
    for h in range(24):
        row = base.iloc[h].to_dict()
        row.update(
            {
                "load": float(load_d.iloc[h]),
                "solar": float(solar_d.iloc[h]),
                "wind": float(wind_d.iloc[h]),
                "resload": float(rl_d.iloc[h]),
                "res_share": float((solar_d.iloc[h] + wind_d.iloc[h]) / max(load_d.iloc[h], 1.0)),
                "resload_mean": float(rl_d.mean()),
                "resload_max": float(rl_d.max()),
                "resload_min": float(rl_d.min()),
                "resload_d1": float(rl_d1.iloc[h]),
                "resload_delta": float(rl_d.iloc[h] - rl_d1.iloc[h]),
                "solar_sum": float(solar_d.sum()),
                "wind_mean": float(wind_d.mean()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


GBM_COLS = [
    "hour",
    "dow",
    "month",
    "holiday",
    "p_d1",
    "p_d2",
    "p_d7",
    "p_d1_mean",
    "p_d1_min",
    "p_d1_max",
    "p_d1_h12",
    "p_d1_h19",
    "p_7d_mean",
]

GBM_COLS_FUND = GBM_COLS + [
    "load",
    "solar",
    "wind",
    "resload",
    "res_share",
    "resload_mean",
    "resload_max",
    "resload_min",
    "resload_d1",
    "resload_delta",
    "solar_sum",
    "wind_mean",
]
