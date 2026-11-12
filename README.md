# Polymer Trade Flow & Disruption Simulator

> **Status: work in progress** (phase 2 of 5: transport LP; Comtrade download partly done, see below)

What happens to polyethylene flows into Europe when the Red Sea closes, and who gains market share?
This project rebuilds global polyethylene trade (HS 3901) from official UN Comtrade statistics,
reconciles contradictory export and import reports, and explains the observed flows with a
cost-minimising transport model (linear programming). Shadow prices from the model act as implied
regional prices, and disruption scenarios (Suez/Red Sea closure, Panama Canal drought, tariffs,
plant outages, oil shocks) show how flows, costs and prices shift. Results will be explorable in an
interactive Dash app.

## Shipping chokepoint monitor

![Shipping chokepoint monitor](docs/figures/monitor_screenshot.jpg)

A Dash app that tracks daily vessel transits through 28 maritime chokepoints (IMF PortWatch)
against their 2019–2023 normal: map of current deviations, 7-day averages with a normal band,
and the Red Sea diversion (share of container ships taking the Cape route: ~25 % before the
crisis, ~77 % since 2024).

```bash
uv run python -m ptf.pipeline portwatch   # download/update transits (incremental)
uv run python -m ptf.app                  # open http://127.0.0.1:8050
```

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
cp .env.example .env             # optional: no API key needed for UN Comtrade
uv run pre-commit install        # run lint/format checks on every commit
uv run pytest                    # run tests
uv run ruff check .              # lint
uv run ruff format .             # format
```

### Data pipeline

```bash
uv run python -m ptf.pipeline ingest   # download raw data (cached, resumable)
uv run python -m ptf.pipeline clean    # raw -> clean layer (Parquet in data/clean)
uv run python -m ptf.pipeline report   # docs/data_quality.md + docs/figures
uv run python -m ptf.pipeline model    # transport LP -> docs/model_results.md
uv run python -m ptf.pipeline portwatch  # chokepoint transits for the monitor app
uv run python -m ptf.pipeline all      # all three steps
```

The public UN Comtrade endpoint has a daily request quota of roughly 100 requests. A full
download (30 reporters × 6 years) therefore takes two days: `ingest` stops cleanly when the
quota is used up and continues where it stopped on the next run.

Results so far: [data-quality report](docs/data_quality.md) ·
[model results](docs/model_results.md) ·
methodology: [docs/methodology.md](docs/methodology.md) ·
all tables and columns: [docs/data_dictionary.md](docs/data_dictionary.md)

## Roadmap

| Phase | Content | Status |
|---|---|---|
| 0 | Repo scaffold, tooling, CI | done |
| 1 | Ingest, cleaning, data-quality report | code done, download ~60 % |
| 2 | Transport LP, model vs. reality, shadow prices | first version done (base year 2023) |
| 3 | Scenarios, cost curves, Dash app (MVP) | started: shipping monitor tab done |
| 4 | Import forecasting (optional) | planned |
| 5 | Docker, Airflow, final polish | planned |
