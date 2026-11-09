"""Equity curve + drawdown figure from long-window dumps (paper trading)."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def equity_and_drawdown_figure(
    equities: Mapping[str, pd.Series],
    *,
    title: str = "GridPilot paper equity (net of stated costs)",
    outfile: Path | str | None = None,
    max_series: int = 6,
) -> Path | None:
    """Plot cumulative cash and drawdown for up to ``max_series`` strategies.

    Returns the output path when ``outfile`` is set; otherwise None.
    """
    items = list(equities.items())[:max_series]
    if not items:
        raise ValueError("equities is empty")

    fig, (ax0, ax1) = plt.subplots(
        2,
        1,
        figsize=(10, 6),
        sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1.0]},
    )
    for name, eq in items:
        s = pd.Series(eq).dropna().astype(float).sort_index()
        if s.empty:
            continue
        ax0.plot(s.index, s.to_numpy(), label=name, linewidth=1.2)
        dd = s.cummax() - s
        ax1.plot(dd.index, dd.to_numpy(), label=name, linewidth=1.0)

    ax0.set_ylabel("Cash €")
    ax0.set_title(title)
    ax0.legend(loc="upper left", fontsize=8, frameon=False)
    ax0.grid(True, alpha=0.3)
    ax1.set_ylabel("Drawdown €")
    ax1.set_xlabel("Time")
    ax1.grid(True, alpha=0.3)
    fig.tight_layout()

    if outfile is None:
        plt.close(fig)
        return None
    out = Path(outfile)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out
