# Changelog

Notable changes per version. Format based on "Keep a Changelog"; versions follow semantic
versioning (`0.x`: no stable interface yet).

## Unreleased

### Added
- Strict type checking with mypy (CI and pre-commit), coverage threshold of 85 % in CI.
- Working agreement: feature specs in `specs/`, branch/PR workflow, Definition of Done,
  PR template (ADR-010).
- Tests for the BACI and GSCPI downloads and the pipeline command line.

- ADR-011: data model and transformations in SQL with dbt on DuckDB (star schema);
  spec 002 for the first increment (trade data).

### Changed
- Shared test fakes moved to `tests/helpers.py`; optional app tables are checked with
  `require()` instead of being used unchecked.

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
