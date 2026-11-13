# Changelog

Notable changes per version. Format based on "Keep a Changelog"; versions follow semantic
versioning (`0.x`: no stable interface yet).

## Unreleased

### Added
- Landed-cost tab (spec 007): price (BACI unit value, optionally indexed to today), sea
  freight and EU duty per supplier country in EUR/t, with Red Sea open/closed and a freight
  factor; duty rates in `config/sourcing.yaml`.
- Route variant `red_sea_closed` (`config/model.yaml`), written by `ptf ingest` as a second
  sea-distance table.
- Buyer dashboard (spec 006): tabs "Situation" (traffic lights for price, supply and
  logistics, "what changed"), "Prices & drivers" (EUR/USD switch, feedstock vs. resin
  indexed to 2019) and "Sourcing" (import sources treemap, Sankey of routes, share of
  imports through disrupted chokepoints).
- `ptf.insights` layer for logic that combines domains (ADR-014); `config/sourcing.yaml`.
- dbt mart `mart_import_sources` with tests (`value_between`, shares sum to 1).
- Route passages (`passages`) in the sea-distance table; FRED series `DEXUSEU` and
  `PCU325211325211`.

### Changed
- Tabs "Overview" and "Energy & freight" replaced by "Situation" and "Prices & drivers";
  app title "Polyethylene supply chain monitor".

## 0.4.0 – 2026-11-13

Architecture release: data model in dbt, package structure by domain, Docker. Results of the
model and the monitor are unchanged (parity checks in every step).

### Added
- dbt project on DuckDB (`dbt/`, ADR-011): staging models and a star schema for trade
  (spec 002: `dim_country`, `dim_region`, `dim_product`, `fct_trade`, marts for analysis and
  the LP) and for shipping and markets (spec 003: `dim_chokepoint`, `dim_port`,
  `dim_market_series`, `dim_date`, facts for transits, port activity, market prices, port
  links and events, app marts); organised by domain with tags; 110 nodes with dbt tests.
- Docker image built with uv in two stages, `compose.yaml` with the services `app`
  (gunicorn, healthcheck) and `pipeline` (any `ptf` step), data on volumes; CI builds the
  image and runs `docker/smoke_test.sh` (spec 005, ADR-013).
- `uv run ptf <step>` as command (also `python -m ptf <step>`).
- Settings `APP_HOST`, `APP_PORT`, `DBT_PROJECT_DIR`; the app shows a start page when the
  warehouse has no data yet.
- Quality gates: strict type checking with mypy, coverage threshold of 85 %, package
  dependency rules with import-linter (ADR-012), all in CI and pre-commit.
- Working agreement: feature specs in `specs/`, branch/PR workflow, Definition of Done,
  PR template (ADR-010).
- Tests for the BACI and GSCPI downloads and the command line.

### Changed
- Package organised by domain (spec 004, ADR-012): `core`, `trade`, `shipping`, `markets`,
  `model`, `legacy`, `app`, with one `steps.py` per domain and a thin `ptf.cli` instead of
  `ptf.pipeline`; the Comtrade check moved to `ptf.legacy.comtrade`.
- One configuration file per domain: `config/pipeline.yaml` split into `trade.yaml` and
  `comtrade.yaml`; `monitor.yaml` -> `shipping.yaml`, `market_data.yaml` -> `markets.yaml`.
- The transport LP, the data-quality report and the Dash app read from the warehouse marts;
  `ptf clean` / `portwatch` / `market` run `dbt build` for their domain.
- `ptf ingest` no longer downloads Brent; `ptf market` already fetches the same FRED series.
- The package version is read from `pyproject.toml` (it still said 0.1.0 at v0.3.0).
- Shared test fakes moved to `tests/helpers.py`; optional app tables are checked with
  `require()` instead of being used unchecked.

### Removed
- pandas implementation of the BACI cleaning (`ptf.clean.baci`) and the files
  `trade_hs6.parquet` / `bilateral_flows.parquet`, after a parity check (identical results).
- pandas cleaning of PortWatch and market data (`ptf.clean.portwatch`, `ptf.clean.market`,
  `ptf.clean.brent`) and their clean Parquet files, after a parity check (identical results).

## 0.3.0 – 2026-11-13

### Added
- Trade data from CEPII BACI (all countries, split by polyethylene type), replacing the own
  Comtrade download, which remains as a check (ADR-009).
- Dash dashboard with five tabs: overview, chokepoints, ports, trade flows, energy & freight
  (IMF PortWatch, FRED, NY Fed GSCPI; ADR-006 to ADR-008).
- Transport LP (Pyomo + HiGHS) with regional prices and scarcity rents (ADR-005).

## 0.1.0 – 2026-11-12

### Added
- Project scaffold: uv, ruff, pytest, pre-commit, CI, settings, specification (ADR-001, ADR-002).
