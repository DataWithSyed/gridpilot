"""Light Streamlit dashboard for a paper simulator run (no real orders)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# Prefer a completed run so the UI stays memory-light.
def _default_run() -> Path:
    here = Path(__file__).resolve()
    for cand in here.parents:
        p = cand / "packages" / "simulator" / "results" / "sim_run.json"
        if p.exists():
            return p
        if (cand / "packages" / "core").exists():
            return p
    return Path("packages/simulator/results/sim_run.json")


def load_run(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data.get("actions"), list):
        data["actions"] = pd.DataFrame(data["actions"])
        if len(data["actions"]) and "ts" in data["actions"].columns:
            data["actions"]["ts"] = pd.to_datetime(data["actions"]["ts"])
    return data


def render(data: dict) -> None:
    import streamlit as st
    import matplotlib.pyplot as plt

    sc = data.get("scenario") or {}
    st.set_page_config(page_title="GridPilot paper simulator", layout="wide")
    st.title("GridPilot paper simulator")
    st.warning(
        "Paper trading only. No exchange connectivity, no real orders, no real-money performance. "
        "Day-ahead only. Perfect foresight is an oracle with lookahead; the agent never uses it."
    )
    if sc.get("kind") == "synthetic":
        st.info(f"SYNTHETIC scenario **{sc.get('name')}** — not Energy-Charts market data. {sc.get('description')}")
    else:
        st.caption(sc.get("attribution") or "")

    pnl = data.get("pnl") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ML net €", f"{pnl.get('ml_net_eur', 0):,.2f}")
    c2.metric("Threshold net €", f"{pnl.get('threshold_net_eur', 0):,.2f}")
    c3.metric("PF oracle net €", f"{pnl.get('perfect_foresight_net_eur', 0):,.2f}")
    c4.metric("Capture of PF", f"{data.get('capture_vs_pf_net_pct') or 0:.1f}%")

    actions = data.get("actions")
    if isinstance(actions, pd.DataFrame) and len(actions):
        left, right = st.columns(2)
        with left:
            st.subheader("Price and SoC")
            fig, ax = plt.subplots(figsize=(7, 3.2))
            ax.plot(actions["ts"], actions["price"], label="DA price", color="#1f4e79")
            ax.set_ylabel("€/MWh")
            ax2 = ax.twinx()
            ax2.plot(actions["ts"], actions["soc"], label="SoC", color="#2e7d32")
            ax2.set_ylabel("SoC")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
        with right:
            st.subheader("Cumulative net P&L")
            eq = data.get("equity") or {}
            fig, ax = plt.subplots(figsize=(7, 3.2))
            for k, lab, col in (
                ("ml_net", "ML net", "#1f4e79"),
                ("threshold_net", "Threshold net", "#c77800"),
                ("perfect_foresight_net", "PF oracle", "#6a1b9a"),
            ):
                if k in eq:
                    ax.plot(actions["ts"], eq[k], label=lab, color=col)
            ax.legend(fontsize=8)
            ax.set_ylabel("€")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

        st.subheader("Forecast fan (P10 / P50 / P90) at each gate closure")
        fans = data.get("forecasts") or {}
        if fans:
            day = st.selectbox("Delivery day", list(fans.keys()))
            fan = fans[day]
            idx = pd.to_datetime(fan.get("index", []))
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.fill_between(idx, fan["p10"], fan["p90"], color="#90caf9", alpha=0.5, label="P10–P90")
            ax.plot(idx, fan["p50"], color="#1565c0", label="P50")
            ax.legend(fontsize=8)
            ax.set_ylabel("€/MWh")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.caption("No gate-closure forecasts in this run (window shorter than D-1 12:00).")

        st.subheader("Decisions and risk")
        show = actions[["ts", "price", "charge_mw", "discharge_mw", "soc", "cycles", "killed"]].copy()
        st.dataframe(show, use_container_width=True, hide_index=True)

    ev = data.get("events") or []
    st.subheader("Events (gate closure, data outage, kill switch)")
    st.json(ev)
    st.caption("Cost preset and limitations")
    st.json({"costs": data.get("costs"), "limitations": data.get("limitations"), "risk": data.get("risk")})


def main() -> None:
    import streamlit as st

    path = st.sidebar.text_input("Run JSON", str(_default_run()))
    p = Path(path)
    if not p.exists():
        st.error(f"No run file at {p}. First run:  gridpilot-sim run --scenario normal --speed 0 --seed 0")
        return
    render(load_run(p))


if __name__ == "__main__":
    main()
