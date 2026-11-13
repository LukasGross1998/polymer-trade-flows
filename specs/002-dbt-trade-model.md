# 002 – dbt warehouse, first increment: trade data (BACI)

- **Status:** done
- **Branch / PR:** `feat/dbt-trade-model`
- **SPEC.md sections:** 3 (data pipeline), 4 (model inputs)

## Goal

Introduce the dbt project on DuckDB and move the trade data (BACI) from pandas functions to
SQL models with an explicit star schema. The transport LP reads its input from the new mart.

## Acceptance criteria

1. `uv run dbt build` (inside `dbt/`) creates `data/warehouse.duckdb` with the schemas
   `staging` and `marts` and runs all dbt tests without failure.
2. Python writes only a landing file: BACI HS 3901xx flows unchanged from the zip
   (`raw/baci/landing_hs3901.parquet`) plus the region reference from `config/regions.yaml`.
3. Marts: `dim_country` (ISO3, name, region), `dim_region`, `dim_product` (HS6, name),
   `fct_trade` (year, exporter, importer, HS6, value USD, quantity t, imputed flag) and
   `mart_region_trade` (year, exporter region, importer region, quantity t).
4. dbt tests: unique and not-null keys on all dimensions and on `fct_trade`
   (year + exporter + importer + HS6); relationships from `fct_trade` to `dim_country` and
   `dim_product`; quantity ≥ 0; every country maps to exactly one region.
5. **Parity:** `mart_region_trade` equals the region totals of today's `bilateral_flows`
   (pandas) for every year within 0.01 %; the imputed quantities match too.
6. `run_model` reads `mart_region_trade`; the LP results for 2023 are unchanged.
7. CI runs `dbt build` on the fixture data; the pandas functions `to_bilateral_flows` and
   `impute_quantities` are removed once parity holds.
8. Column descriptions in dbt YAML; `docs/data_dictionary.md` points to them for the
   warehouse tables.

## Out of scope

PortWatch, market data and the app (next increments); monitor metrics in SQL; Docker and
Airflow.

## Design notes

- `dbt/` project at the repository root; `profiles.yml` in the project, path to the DuckDB
  file from an environment variable (default `data/warehouse.duckdb`).
- Staging reads the landing Parquet via a dbt source (`read_parquet`).
- Imputation of missing quantities as a window median per year and HS6 in SQL.
- Check before starting: dbt-duckdb with DuckDB 2.0 and dbt-core 1.12.

## Result

- `dbt build`: 8 models, 1 seed, 34 tests, all passing in about 5 s on the real data.
- Parity: all 34,341 relations and 92,947 product flows identical to the pandas tables,
  largest difference 5 × 10⁻¹⁰ t; LP results for 2023 unchanged (42 % explained).
- dbt runs as a subprocess (`ptf.warehouse.run_dbt`): in-process `dbtRunner` kept a DuckDB
  connection open that blocked reading the warehouse afterwards.
