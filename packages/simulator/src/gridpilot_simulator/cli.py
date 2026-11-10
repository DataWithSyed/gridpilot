"""CLI: gridpilot-sim run | dashboard | report. Paper trading only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _umbrella() -> Path:
    # packages/simulator/src/gridpilot_simulator/cli.py → repo root is parents[4]
    here = Path(__file__).resolve()
    for cand in here.parents:
        if (cand / "packages" / "core" / "src").exists() and (cand / "pyproject.toml").exists():
            return cand
    return here.parents[4]


def _prepare() -> Path:
    root = _umbrella()
    sys.path.insert(0, str(root / "packages"))
    from _srcpaths import add_src_paths

    add_src_paths(root)
    return root


def main(argv: list[str] | None = None) -> None:
    root = _prepare()
    from gridpilot_simulator.engine import SimConfig, run_simulation
    from gridpilot_simulator.report import write_reports
    from gridpilot_simulator.scenarios import SCENARIOS, load_scenario

    p = argparse.ArgumentParser(
        description="GridPilot paper market simulator (no real orders)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Replay a scenario tick by tick")
    run.add_argument("--scenario", default="normal", help=f"One of: {', '.join([*SCENARIOS, 'historical'])}")
    run.add_argument("--speed", type=float, default=0.0, help="Sim seconds per wall second (0=as fast as possible). e.g. 1, 60, 1000")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--days", type=int, default=7)
    run.add_argument("--out", type=Path, default=None)
    run.add_argument("--cache", type=Path, default=None, help="Hourly DE-LU cache for --scenario historical")
    run.add_argument("--policy", default="cost_aware", choices=("cost_aware", "quantile_bids", "cvar", "id_reopt"),
                    help="Agent policy locked at gate closure (paper only)")
    run.add_argument("--cvar-lambda", type=float, default=2.0)

    sub.add_parser("dashboard", help="Launch the Streamlit dashboard")
    rep = sub.add_parser("report", help="Rebuild HTML/PNG from a sim_run.json")
    rep.add_argument("json_path", type=Path)
    rep.add_argument("--out", type=Path, default=None)

    args = p.parse_args(argv)
    if args.cmd == "dashboard":
        _launch_dashboard(root)
        return
    if args.cmd == "report":
        data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
        # report() expects a light summary; skip actions DataFrame rebuild if present as records
        import pandas as pd
        if "actions" in data and isinstance(data["actions"], list):
            data["actions"] = pd.DataFrame(data["actions"])
        if "equity" in data:
            data["equity"] = {k: pd.Series(v) for k, v in data["equity"].items()}
        out = args.out or Path(args.json_path).parent
        paths = write_reports(data, out)
        print("wrote", {k: str(v) for k, v in paths.items()})
        return

    out = args.out or (root / "packages" / "simulator" / "results")
    kwargs = {"seed": args.seed, "days": args.days}
    if args.scenario in {"historical", "energy_charts"}:
        cache = args.cache or (root / "packages" / "forecast" / "data" / "cache" / "de_lu_hourly.csv.gz")
        kwargs = {"cache": cache}
        # load_scenario historical doesn't take seed/days the same way
        scen = load_scenario("historical", cache=cache)
    else:
        scen = load_scenario(args.scenario, seed=args.seed, days=args.days)
    cfg = SimConfig(speed=args.speed, seed=args.seed, policy=args.policy, cvar_lambda=args.cvar_lambda)
    if scen.name == "forecast_failure":
        cfg.forecast_bias = 80.0
    print(
        f"gridpilot-sim run scenario={scen.name} kind={scen.kind} ticks={len(scen.prices)} "
        f"speed={cfg.speed} seed={cfg.seed} policy={cfg.policy} (paper only)",
        flush=True,
    )
    summary = run_simulation(scen, cfg)
    paths = write_reports(summary, out)
    pnl = summary["pnl"]
    print(
        f"ML net {pnl['ml_net_eur']:.2f} €  |  threshold net {pnl['threshold_net_eur']:.2f} €  |  "
        f"PF oracle net {pnl['perfect_foresight_net_eur']:.2f} €  "
        f"(paper only, not real-money)",
        flush=True,
    )
    print("wrote", {k: str(v) for k, v in paths.items()}, flush=True)


def _launch_dashboard(root: Path) -> None:
    app = root / "packages" / "simulator" / "src" / "gridpilot_simulator" / "dashboard.py"
    try:
        from streamlit.web import cli as stcli
    except Exception as exc:  # pragma: no cover
        raise SystemExit("Streamlit is required: pip install -e '.[ui]'") from exc
    sys.argv = ["streamlit", "run", str(app), "--server.headless=true"]
    stcli.main()


if __name__ == "__main__":
    main()
