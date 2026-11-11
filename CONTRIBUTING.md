# Contributing to GridPilot

Thanks for interest in improving GridPilot. This is a **paper-trading** research stack. Start with the [README](README.md) and the [docs index](docs/index.md).

## Ground rules

1. **Paper trading only.** Do not open PRs that place, route, or sign real market orders. Live-exchange execution is explicitly out of scope. There is no exchange connectivity in this repository, and adding it is not a welcome change.
2. **No secrets.** API tokens (for example a future `ENTSOE_API_TOKEN`) belong in environment variables. Never commit credentials, cookies, or private keys.
3. **No fabricated numbers.** README and results figures must come from a real script run already in the repo, or from a new run whose output is committed next to the text. Label modelling defaults **ASSUMED** with a short source note. If two experiments use different fans, hour counts, or cycle clips, say so — do not present them as one path.
4. **Respect data licences.** Energy-Charts / SMARD DE-LU prices and public-power forecasts are [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — attribute them. Refuse or gate non-CC BY zones.
5. **Link, don’t fork-duplicate.** Prefer adapters that call or cite prior DataWithSyed energy repos instead of copying their studies wholesale.
6. **Small PRs.** One module or fix per PR when possible. Update the relevant docs (`docs/RESULTS.md` when numbers change, `CHANGELOG.md` for user-visible work).
7. **Do not add `.github/workflows`.** This project’s publishing token cannot push GitHub Actions workflows. Issue templates live under [`docs/issue-templates/`](docs/issue-templates/).

## Dev loop

From the repository root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ui]"
pytest -q
```

Useful entry points after that install:

```bash
gridpilot-backtest --help
gridpilot-live-pilot --help
gridpilot-sim run --scenario normal --speed 0 --seed 0
gridpilot-sim dashboard
```

The paper simulator can also be started with `./packages/simulator/scripts/quickstart.sh` or the Docker path in the README. Heavy 12-month walk-forwards are optional and memory-hungry; do not re-run them just to typo-fix a doc. Prefer the committed JSON/Markdown under `packages/forecast/results/` and `results/live/`.

## Documentation

- Package overview and data flow: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Methods (forecast, LPs, CIs): [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)
- Measured tables and source files: [`docs/RESULTS.md`](docs/RESULTS.md)
- Fees and citations: [`docs/fees.md`](docs/fees.md)
- Terms: [`docs/GLOSSARY.md`](docs/GLOSSARY.md)

Each `packages/*/README.md` should link back to [`docs/index.md`](docs/index.md) and the umbrella README. Keep limitations honest: coverage still below 80%, no public ID or official reBAP series in the published runs, degradation still assumed at 5 €/MWh, and gate-closure bid curves under-cycled versus the locked schedule.

## Code style (light)

- Python 3.10+. Prefer clear names over cleverness.
- Tests live under each package’s `tests/` directory and are collected from the root `pyproject.toml`.
- New strategy or LP behaviour needs a focused unit test, not only a long backtest.
- Do not commit caches, secrets, or `packages/*/results/` event streams that the `.gitignore` already excludes.

## Issue templates

Use the markdown templates under [`docs/issue-templates/`](docs/issue-templates/).

## Code of conduct (short)

Be precise, be kind, prefer evidence over vibes. Energy markets are adversarial enough already.
