# 004 – Package structure by domain

- **Status:** done
- **Branch / PR:** `refactor/package-by-domain` / see PR
- **SPEC.md sections:** 9 (architecture), 10 (next steps, step 3); ADR-012

## Goal

The Python package is organised by domain (`trade`, `shipping`, `markets`, `model`) instead
of a mix of technical layers (`ingest/`, `clean/`) and topics, with one shared `core` and the
superseded Comtrade check isolated in `legacy`. A change to one data source touches one
package; the command line becomes a thin registry of steps. Behaviour does not change.

## Acceptance criteria

1. Every module lives in exactly one of `ptf.core`, `ptf.trade`, `ptf.shipping`,
   `ptf.markets`, `ptf.model`, `ptf.legacy`, `ptf.app` or is the entry point `ptf.cli`;
   the packages `ptf.ingest`, `ptf.clean`, `ptf.monitor`, `ptf.market` and the top-level
   modules `config`, `market_config`, `pipeline_config`, `regions`, `warehouse`, `pipeline`
   no longer exist.
2. Dependency rules are checked automatically (import-linter, CI and pre-commit):
   - `core` imports no other `ptf` package;
   - the domains import `core` but not each other, not `app` and not `cli`;
   - `legacy` is imported by `cli` only.
3. Each domain owns its configuration file: `config/trade.yaml`, `config/shipping.yaml`,
   `config/markets.yaml`, `config/model.yaml`; `config/regions.yaml` is shared (core);
   `config/comtrade.yaml` belongs to legacy. `config/pipeline.yaml` is gone.
4. `uv run ptf <step>` and `uv run python -m ptf <step>` accept the same steps as the old
   `python -m ptf.pipeline` (`ingest`, `clean`, `report`, `model`, `portwatch`, `market`,
   `comtrade`, `all`); `all` runs the steps in the same order and still excludes `comtrade`.
   An unknown step exits with an error.
5. Results are unchanged: all existing tests pass with only import paths and setup adapted,
   the full `dbt build` on the fixtures passes, coverage stays ≥ 85 %.

## Out of scope

- No new features, no changed numbers, no new data sources.
- No renaming of dbt models or warehouse tables.
- The app keeps its structure (`app/tabs/*`); only its imports change.
- Typer or another CLI framework: argparse is enough for eight step names.

## Design notes

| Old | New |
|---|---|
| `config.py`, `ingest/http.py`, `warehouse.py` (dbt + reading), `regions.py` | `core/settings.py`, `core/http.py`, `core/warehouse.py`, `core/regions.py` |
| `to_markdown` in `clean/dq_report.py` | `core/markdown.py` (used by trade and model) |
| `ingest/baci.py`, `clean/dq_report.py`, region reference tables, `BaciConfig` | `trade/baci.py`, `trade/quality_report.py`, `trade/reference.py`, `trade/config.py` |
| `ingest/portwatch.py`, `monitor/*`, port reference table | `shipping/portwatch.py`, `shipping/{config,metrics,flows,overview,vocabulary}.py`, `shipping/reference.py` |
| `ingest/fred.py`, `ingest/gscpi.py`, `market/indicators.py`, `market_config.py`, series reference | `markets/{fred,gscpi,indicators,config,reference}.py` |
| `ingest/distances.py`, `model/*` | `model/distances.py`, `model/*` |
| `ingest/comtrade.py`, `clean/{comtrade,mirror,quality,reconcile}.py` | `legacy/comtrade/{ingest,clean,mirror,quality,reconcile,config}.py` |
| `pipeline.py` | `cli.py` (registry) + `steps.py` per domain |

- Each step function takes only `Settings` and loads its own configuration, so the CLI and
  later Airflow can call it without knowing the domain's internals.
- `regions.yaml` is shared reference data (trade reference tables, model distances, legacy
  reconciliation), so it sits in `core`; it holds no domain logic.
- The Brent download in `ingest` is dropped: `market` already downloads the same FRED series
  (`DCOILBRENTEU`) into the same raw folder, and only the market marts use it.
- Files are moved with `git mv` so that `git log --follow` keeps their history.
