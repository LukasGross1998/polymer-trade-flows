# Polymer Trade Flow & Disruption Simulator

> **Status: work in progress** (phase 0 of 5: project scaffold)

What happens to polyethylene flows into Europe when the Red Sea closes, and who gains market share?
This project rebuilds global polyethylene trade (HS 3901) from official UN Comtrade statistics,
reconciles contradictory export and import reports, and explains the observed flows with a
cost-minimising transport model (linear programming). Shadow prices from the model act as implied
regional prices, and disruption scenarios (Suez/Red Sea closure, Panama Canal drought, tariffs,
plant outages, oil shocks) show how flows, costs and prices shift. Results will be explorable in an
interactive Dash app.

## Approach

1. **Data:** UN Comtrade bilateral trade -> cleaning, mirror statistics, imputation -> Parquet/DuckDB
2. **Model:** transport LP in Pyomo, solved with HiGHS; duals interpreted as regional prices
3. **Scenarios:** declarative YAML scenarios, cost curves, before/after comparison
4. **App:** Dash + Plotly

The full specification is in [SPEC.md](SPEC.md); design decisions are in
[docs/decisions.md](docs/decisions.md).

## Tech stack

Python 3.12 · uv · pandas · Parquet + DuckDB · Pyomo + HiGHS · Dash + Plotly ·
pytest · ruff · pre-commit · GitHub Actions · later Docker and Airflow

## How to run

Prerequisites: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 automatically).

```bash
git clone <repo-url>
cd polymer-trade-flows
uv sync                          # create .venv and install dependencies
cp .env.example .env             # then add your UN Comtrade API key
uv run pre-commit install        # run lint/format checks on every commit
uv run pytest                    # run tests
uv run ruff check .              # lint
uv run ruff format .             # format
```

## Roadmap

| Phase | Content | Status |
|---|---|---|
| 0 | Repo scaffold, tooling, CI | done |
| 1 | Ingest, cleaning, data-quality report | planned |
| 2 | Transport LP, model vs. reality, shadow prices | planned |
| 3 | Scenarios, cost curves, Dash app (MVP) | planned |
| 4 | Import forecasting (optional) | planned |
| 5 | Docker, Airflow, final polish | planned |
