# 003 – dbt warehouse, second increment: shipping (PortWatch) and market data

- **Status:** done
- **Branch / PR:** `feat/dbt-shipping-markets`
- **SPEC.md sections:** 7a, 7b (dashboard data), 3 (data pipeline)
- **ADR:** ADR-011 (dbt on DuckDB)

## Goal

Move the cleaning of the PortWatch and market data from pandas functions to dbt, extend the
star schema with the shipping and market dimensions and facts, and let the Dash app read the
warehouse instead of individual Parquet files. Afterwards the app and the LP read from one
database.

## Acceptance criteria

1. **Sources without Python cleaning:** dbt reads the PortWatch raw downloads directly
   (`read_parquet` over each folder, e.g. `portwatch/chokepoints_daily/*.parquet`) and keeps
   the most recently fetched row per day and location in SQL. FRED series are read from the
   newest CSV per series. Only the NY Fed GSCPI (old `.xls` format that DuckDB cannot read) and
   the series metadata from `config/market_data.yaml` get a small Python landing step.
2. **Star schema extended:** dimensions `dim_chokepoint`, `dim_port` (configured ports with
   name and role), `dim_market_series` (name, unit, frequency, group), `dim_date` (calendar
   days covered by the data); facts `fct_chokepoint_transits` (day × chokepoint),
   `fct_port_activity` (day × port), `fct_market_prices` (date × series),
   `fct_port_links` (directed port pair, snapshot), `fct_disruption_events` (event).
3. **App marts** with the column names the app and the monitor metrics use today
   (`mart_chokepoint_transits`, `mart_port_activity`, `mart_market_series`, ...), so that
   `ptf.monitor` stays unchanged; `brent_annual` becomes the mart `mart_brent_annual`.
4. **dbt tests:** keys unique and not null (day + chokepoint, day + port, date + series,
   link pair, event id); relationships to the new dimensions; counts and volumes ≥ 0;
   accepted values for vessel types and alert levels.
5. **Parity** with today's clean Parquet files on the real data: identical row counts and
   values (within floating-point noise) for transits, port activity, events, port links and
   market series; monitor KPIs (e.g. Bab el-Mandeb container traffic −67 % vs. normal,
   6 of 28 chokepoints disrupted) unchanged.
6. **App reads the warehouse** (`ptf.app.data.load_app_data` via `ptf.warehouse.read_table`);
   tables that do not exist yet (e.g. country trade while switched off) still lead to a hint
   instead of an error. The warehouse connection is opened read-only and closed after
   loading, so `dbt build` can run while the app is open.
7. `pipeline portwatch` and `pipeline market` = download + `dbt build`; the pandas cleaning
   functions for PortWatch and market data are removed once parity holds.
8. Tests: the fixture raw layer contains small PortWatch, FRED and GSCPI raw files; the
   session warehouse fixture builds all marts; app tests run against the warehouse; coverage
   stays ≥ 85 %; dbt YAML documents every new mart column (checked by the docs test).

## Out of scope

Monitor metrics (rolling means, seasonal baseline) in SQL – they stay in Python (ADR-011);
Docker, Airflow; country trade by cargo type stays optional (model disabled while the
download is switched off).

## Design notes

- Deduplication in SQL: `qualify row_number() over (partition by date, portid order by
  fetched_at desc) = 1`.
- FRED: `read_csv('fred/*/*.csv', filename = true)`; series id from the folder name, newest
  file per series via the file name (download time stamp).
- Optional country trade: dbt variable `country_trade_enabled` (default false) mirrors
  `download_country_trade` in `config/monitor.yaml`; the model is disabled without data.
- `dim_date` from the earliest to the latest date in the facts (DuckDB `range()`).
- Risk: a folder without any file makes `read_parquet` fail; the pipeline only builds marts
  whose raw folders exist (or the source is guarded by a variable).

## Result

- `dbt build`: all models and tests of trade, shipping and markets pass (110 nodes).
- Parity with the removed pandas cleaning on the real data: transits (80,332 rows), port
  activity (31,537), events (132), port links (8,084), market series (43,310) and Brent annual
  values identical; monitor KPIs unchanged (Bab el-Mandeb container −67 % vs. normal, 6 of 28
  chokepoints disrupted).
- Lessons: dbt-duckdb fills `{name}` in `external_location` via `str.format`, so curly braces
  in a source definition break it (FRED types are cast in staging instead); `group` is an SQL
  keyword and needs `quote: true` for generated tests.
