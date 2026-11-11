# gridpilot-dashboard (umbrella package)

Streamlit ops view for GridPilot. **Logic is in `gridpilot_dashboard`** (unit-tested); `app.py` is thin.

> Part of [gridpilot](https://github.com/DataWithSyed/gridpilot) under `packages/dashboard`.

```bash
pip install -e "packages/dashboard[ui]"
python packages/dashboard/scripts/healthcheck.py
streamlit run packages/dashboard/app.py
```

Paper trading only.


## Documentation

Part of the [GridPilot umbrella](../../README.md). Guides, methods, and measured paper results: [`docs/index.md`](../../docs/index.md). Paper trading only — no exchange connectivity and no real-money claims.
