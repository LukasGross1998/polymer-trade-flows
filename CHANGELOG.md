# Changelog

Notable changes per version. Format based on "Keep a Changelog"; versions follow semantic
versioning (`0.x`: no stable interface yet).

## Unreleased

### Changed
- Situation page for European buyers (spec 013): four-level traffic lights (green, yellow,
  orange, red) with new thresholds; a polyethylene card (Dalian LLDPE in EUR); action links
  that open the right tab ("Review drivers →", "Check routes →", "View delays →", "See PE
  prices →"); "What changed" with true 7-day moves of daily series; filter "Relevant for
  Europe" (regions, chokepoints, ports, series, events) with a switch to all regions;
  chokepoint entries with Europe's import share and the Red Sea detour days; method notes
  in info icons instead of a footer; "Last updated" and data dates in the header.

### Added
- Isolated Docker service `asia` (spec 012): image `ptf:asia` (build argument `EXTRAS`),
  step `ptf dce`, only `data/raw/dce` mounted, no `.env`, read-only file system, no
  capabilities; CI builds it and checks the isolation.
- Latest intraday quote of the Dalian LLDPE main contract (last trade, bid, ask, trading
  day) in `mart_dce_quote`, shown on the Prices tab when newer than the daily close.
- Daily LLDPE price from the Dalian Commodity Exchange (spec 011, ADR-015) via AKShare as
  optional extra `asia`: download in `ptf market`, series `DCE_LLDPE` in the market mart,
  chart and KPI in USD or EUR on the Prices tab; CI job with the extra's tests and
  `pip-audit`.
- Order planner (spec 010): tab in the Buying section with landed cost against arrival date
  per supplier country, need-by date, quantity, grade and Red Sea switch; recommendation of
  the cheapest on-time supplier. Lead times from sea distances (14 kn), port days, buffers
  for congested ports and storms on the route, overland days for landlocked exporters;
  ports in `config/shipping.yaml` get a model region.

## 0.5.0 – 2026-11-14

Buyer release: the app answers the questions of a polyethylene buyer in Europe and places
PE in world trade, at chokepoints and in the weather. Specs 006–009.

### Added
- Buyer dashboard (spec 006): tab "Situation" (traffic lights for price, supply and
  logistics; what changed in the last 7 days), "Prices & drivers" (EUR/USD switch,
  feedstock vs. resin indexed to 2019) and "Sourcing" (import sources treemap, Sankey of
  routes, share of imports through disrupted chokepoints).
- `ptf.insights` layer for logic that combines domains (ADR-014); `config/sourcing.yaml`.
- Landed cost (spec 007): price, sea freight and EU duty per supplier country in EUR/t,
  with Red Sea open/closed and a freight factor; route variant `red_sea_closed`.
- Breakdown by class (spec 008): tab "World trade by class" from the whole BACI file
  (tonnes vs. value per commodity class, drill-down to the PE grades); vessel classes at
  chokepoints; PE grade filter in Sourcing and Landed cost.
- Marine weather (spec 009): waves and gusts at all chokepoints and monitored ports, past
  7 days and 7-day forecast, storm warnings; EU third-country duty per grade from World
  Bank WITS (confirms 6.5 %); OpenSeaMap nautical chart layer.
- dbt: marts `mart_import_sources`, `mart_import_sources_by_product`,
  `mart_trade_by_class`, `mart_eu_duty`, `mart_marine_weather`; seeds
  `commodity_classes`, `commodity_class_tree`; tests `value_between`, shares sum to 1.
- Data: route passages in the sea-distance table; FRED `DEXUSEU`, `PCU325211325211`;
  BACI world-trade summary `landing_all_trade`.
- README section "Data sources and keys"; `.env.example` lists `AISSTREAM_API_KEY` and
  `EIA_API_KEY` (not used yet).

### Changed
- Navigation in two sections, "Buying" and "Markets & logistics"; "Overview" and
  "Energy & freight" replaced by "Situation" and "Prices & drivers"; app title
  "Polyethylene supply chain monitor".
- Chokepoint and port maps are tile maps (MapLibre) instead of a plain world map.

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
