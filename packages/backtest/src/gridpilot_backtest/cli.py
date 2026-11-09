"""CLI: gridpilot-backtest — reproducible comparison run."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _setup_path() -> Path:
    here = Path(__file__).resolve()
    # packages/backtest/src/gridpilot_backtest/cli.py -> umbrella (= parents[4])
    umbrella = here.parents[4]
    gp = umbrella.parent
    root_bt = here.parents[2]
    root_fc = umbrella / "packages" / "forecast"
    for p in (
        root_bt / "src",
        root_fc / "src",
        gp / "gridpilot-core" / "src",
        gp / "gridpilot-strategies" / "src",
        gp / "gridpilot-data" / "src",
        gp / "gridpilot-risk" / "src",
    ):
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    return gp


def main(argv: list[str] | None = None) -> None:
    gp = _setup_path()
    from gridpilot_core.agent import PaperAgent
    from gridpilot_core.battery import BatteryConfig
    from gridpilot_core.risk import RiskLimits
    from gridpilot_core.strategy import PerfectForesightDaily, ThresholdArbitrage
    from gridpilot_backtest.harness import BacktestHarness, comparison_table
    from gridpilot_forecast.strategy import MLForecastDrivenLP, MLRiskAwareForecastLP
    from gridpilot_strategies.forecast_lp import ForecastDrivenLP, RiskAwareForecastLP

    try:
        from gridpilot_data.adapters import EnergyChartsAdapter

        def load_prices(start, end, cache):
            return EnergyChartsAdapter(cache_dir=cache).fetch_day_ahead_prices(start, end)
    except Exception:
        from gridpilot_core.data_replay import fetch_day_ahead_prices as _fetch

        def load_prices(start, end, cache):
            return _fetch(start, end, cache_dir=cache)

    ap = argparse.ArgumentParser(description="GridPilot walk-forward backtest (paper trading only)")
    ap.add_argument("--start", default="2026-08-01")
    ap.add_argument("--end", default="2026-10-15")
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--skip-ml", action="store_true", help="Skip ML strategies (faster / less RAM)")
    args = ap.parse_args(argv)

    cache = args.cache or (gp / "gridpilot-core" / "data" / "cache")
    if not cache.exists():
        alt = gp / "gridpilot-data" / "data" / "cache"
        cache = alt if alt.exists() else cache
    prices = load_prices(args.start, args.end, cache)

    strategies = {
        "threshold_arbitrage": ThresholdArbitrage(),
        "forecast_driven_lp": ForecastDrivenLP(),
        "risk_aware_forecast_lp": RiskAwareForecastLP(),
        "perfect_foresight_daily": PerfectForesightDaily(),
    }
    if not args.skip_ml:
        strategies = {
            "threshold_arbitrage": ThresholdArbitrage(),
            "forecast_driven_lp": ForecastDrivenLP(),
            "risk_aware_forecast_lp": RiskAwareForecastLP(),
            "ml_forecast_driven_lp": MLForecastDrivenLP(lookback_days=45, refit_every_days=1),
            "ml_risk_aware_forecast_lp": MLRiskAwareForecastLP(lookback_days=45, refit_every_days=1),
            "perfect_foresight_daily": PerfectForesightDaily(),
        }

    harness = BacktestHarness(
        battery_factory=lambda: BatteryConfig(power_mw=1.0, energy_mwh=2.0),
        risk_factory=lambda: RiskLimits(max_cycles_per_day=2.0, max_drawdown_eur=5000.0),
        agent_factory=lambda b, s, r: PaperAgent(b, s, r),
    )
    results = harness.run(prices, strategies)
    table = comparison_table(results)
    payload = {
        "window": {"start": args.start, "end": args.end, "n_hours": int(len(prices))},
        "battery": "1 MW / 2 MWh",
        "strategies": {k: v.metrics | {
            "capture_vs_pf_pct": float(table.loc[table.strategy == k, "capture_vs_pf_pct"].iloc[0])
            if (table.strategy == k).any() else None
        } for k, v in results.items()},
        "table_csv": table.to_csv(index=False),
        "attribution": "Energy-Charts / SMARD — CC BY 4.0",
        "paper_trading_only": True,
    }
    out = args.out or (Path(__file__).resolve().parents[2] / "results" / "backtest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    table.to_csv(csv_path, index=False)
    # Optional figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        for name, r in results.items():
            if r.equity is not None and len(r.equity):
                ax.plot(r.equity.index, r.equity.values, label=name, linewidth=1.2)
        ax.set_title("Paper-trading equity (1 MW / 2 MWh)")
        ax.set_ylabel("EUR")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig_path = out.parent.parent / "figures" / "equity_comparison.png"
        fig_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(fig_path, dpi=120)
        plt.close(fig)
        payload["figure"] = str(fig_path)
    except Exception as exc:
        payload["figure_error"] = str(exc)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(table.to_string(index=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
