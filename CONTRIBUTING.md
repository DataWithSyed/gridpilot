# Contributing to GridPilot

Thanks for interest in improving GridPilot.

## Ground rules

1. **Paper trading only.** Do not open PRs that place, route, or sign real market orders. Live-exchange execution is explicitly out of scope.
2. **No secrets.** API tokens (e.g. future ENTSO-E) belong in environment variables. Never commit credentials.
3. **No fabricated numbers.** README / results figures must come from a real script run. Label modelling defaults **ASSUMED** with a short source note.
4. **Respect data licences.** Energy-Charts / SMARD DE-LU prices are CC BY 4.0 — attribute. Refuse or gate non-CC BY zones.
5. **Link, don’t fork-duplicate.** Prefer adapters that call or cite prior DataWithSyed energy repos instead of copying their studies wholesale.
6. **Small PRs.** One module or fix per PR when possible. Update the umbrella roadmap checkbox when a step lands.

## Dev loop (per module repo)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Issue templates

Use the markdown templates under [`docs/issue-templates/`](docs/issue-templates/) (this org token cannot push GitHub Actions workflows; templates live in docs on purpose).

## Code of conduct (short)

Be precise, be kind, prefer evidence over vibes. Energy markets are adversarial enough already.
