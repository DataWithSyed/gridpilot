# Changelog

All notable changes to [DataWithSyed/gridpilot](https://github.com/DataWithSyed/gridpilot). Dates follow the git author date (box-local, Asia/Karachi). Built from `git log`; this file does not invent results.

The package version in `pyproject.toml` is **0.5.0**. **Paper trading only** throughout.

## 0.5.0 — 2026-11-14

### Added

- Water-value reservations on gate-closure bid curves: remaining-day cost-aware LP finite difference on the P50 path, bids centred on `η_c · wv − add` / `wv / η_d + add` with the existing fan width. Intra-day only (no terminal SoC value). Simulator hook `--policy water_value_bids`.
- Same-window climatology re-run (2025-11-01 → 2026-10-30, 8,736 h, sourced fees): water-value bids **30,675** € vs locked schedule **60,379** € (**did not beat** the lock, **−81.60 [−99.12, −61.52]** €/day) and vs myopic quantile bids **13,082** € (**improved**, **+48.33 [39.45, 58.87]** €/day). Cycles 212 vs 151 myopic vs 458 locked. Not a re-run of the published cost-aware ML 65,473 € path. The 2026-11-10 ML price-only bid figures were left unchanged (no new walk-forward).

### Documentation

- README, `docs/RESULTS.md`, `docs/BIDDING.md`, `docs/METHODOLOGY.md`, `docs/SIMULATOR.md`, `docs/GLOSSARY.md`, `docs/FAQ.md`, `docs/limitations.md`, and `docs/index.md` updated with the measured water-value result (honest negative vs the lock, honest improvement vs myopic curves).

## Documentation (2026-11-11)

These docs shipped on 0.4.0 as commit `308bb11`; recorded here so the changelog stays dated.

### Documentation (2026-11-11)

- Richer umbrella README: what GridPilot is and is not, architecture diagram, package table, consolidated results, quickstart and Docker, data licences, sourced fee table, limitations and roadmap.
- New guides: `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`, `docs/RESULTS.md`, `docs/GLOSSARY.md`, `docs/FAQ.md`, `docs/index.md`.
- Expanded `CONTRIBUTING.md`. This changelog. Package READMEs link back to the docs index. `docs/limitations.md` refreshed so it no longer contradicts the fundamentals / CQR work.

## 0.4.0 — 2026-11-10

Single public repository. Former sibling packages live under `packages/` and install from the root (`pip install -e ".[dev,ui]"`).

### Added

- Umbrella layout, methods notes, assumptions, and contributing guidelines (`70de190` and related early commits).
- `packages/core`: battery model, `Strategy` protocol, threshold and perfect-foresight baselines, `PaperAgent`, risk limits, P10/P50/P90 daily paper PnL (`fd8700a` and subtree merge).
- `packages/data`: Energy-Charts, replay, and optional ENTSO-E adapters (`8129e96` and subtree merge).
- `packages/risk`: block-bootstrap scenario cash, historical VaR/CVaR, kill-switch hooks (`1ae71d9` and subtree merge).
- `packages/strategies`: climatology forecast-driven and risk-aware LPs with walk-forward evaluation (`6595ae8` and subtree merge).
- `packages/forecast`, `packages/backtest`, and `packages/dashboard` under the umbrella (`691463e`).
- Day-ahead load/solar/wind features, rolling CQR, and the 12-month paper backtest (`97274a6`).
- Near-live paper pilot and accuracy check (`d818901`).
- Assumed fee / slippage / degradation accounting, Mondrian CQR, and equity curves (`76313f5`).
- Cost-aware dispatch LP, tight Mondrian CQR, and a live-pilot fee toggle (`ff98710`).
- Sourced DE-LU fee catalog and a cost-aware re-run under that preset (`6fcc640`).
- Monorepo install: core, data, risk, and strategies merged into one root package (`25d41b0`, after subtree commits `87dd8eb`, `3ecba25`, `62f4895`, `a47467e`).
- `packages/simulator`: tick replay, CLI (`gridpilot-sim`), Streamlit, HTML/PNG report, Docker (`b4355bc`).
- SDAC-style gate-closure bid curves and a same-fan backtest (honest negative versus the locked schedule) (`4acb9fc`).
- Post-DA re-optimisation and a labelled ID / imbalance layer (proxy-only; no public ID or official reBAP series) (`d200be5`).
- Cost-aware CVaR LP and a return-versus-CVaR frontier (`97ee530`).
- Simulator hooks for bid curves, ID re-opt, and CVaR policies (`c61da4b`).

### Notes

- No `.github/workflows` are part of this history (the org token has no workflow scope).
- No release claims real-money performance.
