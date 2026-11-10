# packages/simulator

Real-time **paper** market replay for GridPilot. No exchange connectivity and no real orders.

```bash
# from the umbrella repo root
pip install -e ".[dev,ui]"
gridpilot-sim run --scenario normal --speed 0 --seed 0
gridpilot-sim dashboard
# or: ./packages/simulator/scripts/quickstart.sh
```

See [`docs/SIMULATOR.md`](../../docs/SIMULATOR.md) for the buyer-facing summary and honest limitations.
