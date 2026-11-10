"""JSON/CSV plus a static HTML/PNG demo report. Paper trading only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _jsonable(summary: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in summary.items() if k not in {"actions", "equity"}}
    actions: pd.DataFrame | None = summary.get("actions")
    if actions is not None and len(actions):
        df = actions.copy()
        if "ts" in df.columns:
            df["ts"] = df["ts"].astype(str)
        out["actions"] = df.to_dict(orient="records")
    equity = summary.get("equity") or {}
    out["equity"] = {k: [float(x) for x in ser] for k, ser in equity.items()}
    return out


def write_reports(summary: dict[str, Any], outdir: Path) -> dict[str, Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    js = outdir / "sim_run.json"
    js.write_text(json.dumps(_jsonable(summary), indent=2, default=str) + "\n", encoding="utf-8")
    paths["json"] = js

    actions: pd.DataFrame = summary.get("actions", pd.DataFrame())
    csv = outdir / "sim_run.csv"
    if len(actions):
        actions.to_csv(csv, index=False)
    else:
        csv.write_text("ts\n", encoding="utf-8")
    paths["csv"] = csv

    png = outdir / "demo_dashboard.png"
    _dashboard_png(summary, png)
    paths["png"] = png

    html = outdir / "demo_report.html"
    html.write_text(_html(summary, png.name), encoding="utf-8")
    paths["html"] = html
    return paths


def _dashboard_png(summary: dict[str, Any], path: Path) -> None:
    actions: pd.DataFrame = summary.get("actions", pd.DataFrame())
    equity = summary.get("equity") or {}
    fig, axes = plt.subplots(3, 1, figsize=(11, 8.5), sharex=False)
    fig.suptitle(
        "GridPilot paper simulator — demo (not real-money performance)",
        fontsize=12,
    )
    if len(actions):
        ts = pd.to_datetime(actions["ts"])
        axes[0].plot(ts, actions["price"], color="#1f4e79", lw=1.2, label="DA price")
        axes[0].set_ylabel("€/MWh")
        axes[0].legend(loc="upper left", fontsize=8)
        axes[0].set_title("Price (replay / synthetic as labelled)")
        axes[1].plot(ts, actions["soc"], color="#2e7d32", lw=1.2, label="SoC")
        axes[1].set_ylabel("SoC")
        axes[1].set_ylim(0, 1)
        axes[1].legend(loc="upper left", fontsize=8)
    if equity:
        for key, color, lab in (
            ("ml_net", "#1f4e79", "ML net"),
            ("threshold_net", "#c77800", "Threshold net"),
            ("perfect_foresight_net", "#6a1b9a", "Perfect foresight (oracle)"),
        ):
            ser = equity.get(key)
            if ser is not None and len(ser):
                idx = pd.to_datetime(actions["ts"]) if len(actions) else range(len(ser))
                axes[2].plot(idx, list(ser), color=color, lw=1.2, label=lab)
        axes[2].set_ylabel("€")
        axes[2].legend(loc="upper left", fontsize=8)
        axes[2].set_title("Cumulative paper P&L (net of cost preset)")
    for ax in axes:
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _html(summary: dict[str, Any], png_name: str) -> str:
    sc = summary.get("scenario") or {}
    pnl = summary.get("pnl") or {}
    lim = summary.get("limitations") or []
    ev = summary.get("events") or []
    kills = [e for e in ev if e.get("type") == "kill_switch"]
    rows = "".join(
        f"<tr><th>{k.replace('_',' ')}</th><td>{v if not isinstance(v, float) else f'{v:,.2f}'}</td></tr>"
        for k, v in pnl.items()
    )
    li = "".join(f"<li>{x}</li>" for x in lim)
    kind = sc.get("kind", "")
    banner = (
        "<p><strong>SYNTHETIC scenario — not Energy-Charts market data.</strong></p>"
        if kind == "synthetic"
        else f"<p>{sc.get('attribution','')}</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>GridPilot paper simulator report</title>
<style>
 body {{ font-family: sans-serif; max-width: 960px; margin: 2rem auto; color: #222; }}
 .warn {{ background: #fff3cd; border: 1px solid #e6c35c; padding: 0.8rem 1rem; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
 img {{ max-width: 100%; height: auto; }}
</style></head>
<body>
<h1>GridPilot paper simulator</h1>
<div class="warn"><strong>Paper trading only.</strong> No exchange connectivity, no real orders,
no real-money performance. Day-ahead only. Perfect foresight is an oracle with lookahead;
the agent never sees it.</div>
{banner}
<p>Scenario: <strong>{sc.get('name')}</strong> ({kind}) — {sc.get('description')}</p>
<p>Seed {summary.get('seed')} · ticks {summary.get('n_ticks')} · gate closure {summary.get('gate_closure')}</p>
<h2>Paper P&amp;L</h2>
<table>{rows}</table>
<p>Capture of perfect-foresight net: {summary.get('capture_vs_pf_net_pct')}</p>
<p>Kill-switch events: {len(kills)}{(' — ' + kills[0].get('reason','')) if kills else ''}.</p>
<h2>Dashboard snapshot</h2>
<p><img src="{png_name}" alt="Demo dashboard snapshot"/></p>
<h2>Honest limitations</h2>
<ul>{li}</ul>
</body></html>
"""
