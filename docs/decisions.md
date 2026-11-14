# Architecture Decision Records

Short records of significant decisions: context, decision, consequences.
New decisions are appended; superseded ones are marked, not deleted.

---

## ADR-001: Core tech stack

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** A portfolio project that must show data engineering, optimisation and
production-grade software practices, run locally on a laptop and stay explainable line by line.

**Decision.**

| Concern | Choice | Why |
|---|---|---|
| Python and packages | Python 3.12, **uv** | One fast tool for Python versions, virtual envs and a lock file (`uv.lock`) -> reproducible installs locally and in CI. |
| Storage | **Parquet + DuckDB**, layers `raw -> clean -> model` | Columnar files are small and typed; DuckDB queries them with SQL without a server. The layering mirrors a lakehouse and keeps raw data immutable. |
| Optimisation | **Pyomo + HiGHS** | Pyomo writes the LP close to the maths and gives access to duals; HiGHS is a fast, free, open-source solver installable via pip (`highspy`). |
| App | **Dash + Plotly** | Interactive web app in pure Python; Plotly covers maps (`scattergeo`) and heatmaps. |
| Quality | **pytest, ruff, pre-commit**, type hints | ruff replaces flake8/isort/black in one tool; pre-commit enforces it before every commit; CI repeats the same checks. |
| Configuration | **pydantic-settings** + `.env` | Typed settings with validation; secrets stay in a git-ignored `.env` and are masked via `SecretStr`. |
| Packaging | `src/` layout, package `ptf` | Tests run against the installed package, not against loose files, which catches packaging errors early. |

**Consequences.** Dependencies are added only in the phase that needs them (no speculative
dependencies). Later phases add Docker, docker compose and Airflow.

---

## ADR-002: pandas instead of polars for data processing

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** The data volume is small (a few hundred thousand rows of bilateral trade at most).
Both pandas and polars handle that easily, so performance is not the deciding factor.

**Decision.** Use **pandas**.

**Reasons.**
- **Ecosystem fit:** Plotly/Dash, Pyomo data handling, statsmodels and scikit-learn (phase 4)
  all accept pandas directly, so no conversions are needed at the boundaries.
- **Industry standard:** pandas is what most data science teams and interviewers expect;
  code reviews and pairing are easier.
- **Learning curve:** far more documentation and examples, which matters while learning the
  data stack.
- Heavy aggregations can be pushed down to **DuckDB SQL**, which offsets most of polars'
  advantages for this project size.

**Consequences / guardrails.** Use explicit dtypes when reading data, avoid relying on the
index (use plain columns and `reset_index()`), and prefer method chaining with clear names over
chained in-place assignment, to avoid pandas' common pitfalls (silent type changes,
`SettingWithCopyWarning`).

---

## ADR-003: UN Comtrade public endpoint without API key

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** The SPEC originally assumed a free Comtrade subscription key. Registering and
managing the key adds setup friction, and anyone cloning the repo would need their own key to
reproduce the data.

**Decision.** Use the public preview endpoint
`https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS`, which needs no registration.
`COMTRADE_API_KEY` stays an optional setting for a later switch to the keyed endpoint.

**Consequences.**
- Same underlying data, so mirror statistics and reconciliation remain possible.
- Max. 500 records per request and aggressive throttling (HTTP 429 observed on a second
  request within a second). The ingest therefore requests one reporter and year at a time,
  waits between requests, retries with exponential backoff and caches every response in the
  `raw` layer so each request runs only once.
- The repo is reproducible without credentials.
- *Added in phase 1:* the endpoint also has a **daily quota** (HTTP 403 "Quota Exceeded" after
  roughly 100 requests on 2026-11-12). The ingest stops cleanly on 403 and resumes from the
  cache on the next run; a full download of 30 reporters × 6 years takes about two days.

---

## ADR-004: Phase-1 data sources and layer formats

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** Phase 1 needs country codes, an oil price and a clear contract between the raw
and clean layers. The Comtrade preview API returns only numeric area codes (no ISO codes, no
names). The EIA oil-price API needs a registered key.

**Decision.**
- Country codes come from Comtrade's own reference tables (`partnerAreas`, `Reporters`),
  cached in the raw layer. "Other Asia, nes" (`S19`) is mapped to Taiwan via
  `comtrade_aliases` in `config/regions.yaml`.
- Brent comes from **FRED** (`DCOILBRENTEU`) as a keyless CSV; the raw layer keeps the CSV
  byte for byte.
- Raw Comtrade data is stored as one Parquet file per reporter and year with the API records
  unchanged plus `fetched_at`. One file per request makes the cache trivial: file exists ->
  skip.
- The clean layer has three tables: `trade_reports` (one row per report),
  `mirror` (both reports of a relation side by side) and `bilateral_flows` (one agreed
  quantity per relation). The data-quality report is a **script**, not a notebook, so it is
  tested and can later run as an Airflow task.
- HTTP retries are a small hand-written loop with exponential backoff instead of a retry
  library: fewer dependencies, every line explainable.

**Consequences.** No credentials are needed for any phase-1 source. Cached raw files must be
deleted by hand to pick up late-reported years.

---

## ADR-005: Transport LP set-up

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** Phase 2 needs an LP solver with access to duals, a base year, and a decision on
how to treat the rest-of-world region, which has no representative port.

**Decision.**
- Solver interface: `pyomo.environ.SolverFactory("highs")` (Pyomo 6.10, `highspy` 1.16).
  Duals are read through `model.dual = Suffix(direction=IMPORT)`. Checked against a 3-region
  example solved by hand (`tests/test_transport.py`), including the sign convention: demand
  duals are >= 0 (prices), capacity duals <= 0 (reported as positive rents).
- Regions are split into Comtrade *reporters* and further *members*, so that every country
  is assigned to its geographic region; `ROW` drops from 37 % to 0.4 % of inter-regional trade.
- `ROW` is excluded from the LP; its trade still enters the model regions' demand.
- Base year 2023, the latest year with complete data for the reporters loaded so far.
- All assumptions live in `config/model.yaml` with a `source` field; the model layer
  (`data/model/{year}/`) stores observed region flows, regional balance, route costs and LP
  results as Parquet.

**Consequences.** The base model is deliberately simple and produces a corner solution
(expensive regions shut down completely). Calibration is a separate step (phase 2b).

---

## ADR-006: Shipping monitor with IMF PortWatch and Dash

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** A first interactive app should show current disruptions at maritime
chokepoints. "Real-time" was the wish; free data had to be checked.

**Decision.**
- Source: IMF PortWatch `Daily_Chokepoints_Data` via the public ArcGIS REST API (no key,
  1,000 rows per page). Daily counts with a few days' delay are accurate enough for a
  disruption monitor. Raw AIS streams (true real-time) were rejected: they would require own
  transit detection from millions of positions, a project of its own.
- Incremental download with a 14-day revision window; one raw file per download, file names
  with microseconds and an explicit no-overwrite check (a test caught two downloads in the
  same second overwriting each other).
- Normal level = same calendar week in 2019–2023; minimum traffic of 2 vessels a day before a
  chokepoint can be flagged.
- App structure: `layout.py` (components), `figures.py` (pure functions DataFrame -> figure),
  `callbacks.py` (only wiring; `update_views` is a plain, tested function), `data.py`
  (loading and refresh). Business logic stays in `src/ptf/monitor/`.
- Light theme only for now; palette from the dataviz guidelines (blue = observed, gray =
  normal, red <-> gray <-> blue for deviation; no dual axes).

**Consequences.** The monitor runs offline from the clean layer; "Update data" fetches new
days. The view update takes ~0.2 s for all 28 chokepoints.

---

## ADR-007: Dashboard with four tabs and free market data

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** The monitor should give a fuller picture of the drivers of polyethylene trade
(ports, events, energy, freight) before building scenario models.

**Decision.**
- Sources: IMF PortWatch ports and disruption events (same API as the chokepoints), FRED
  series listed in `config/market_data.yaml`, NY Fed GSCPI. All free, no key.
- Container rate indices (WCI, FBX, SCFI) are **not** used: no free history. The US PPI for
  deep sea freight is the labelled proxy.
- FRED and GSCPI raw files: one file per download, refreshed when older than one day
  (`max_age_days`); Brent for the model now uses the same FRED module.
- The GSCPI file is an old Excel format despite its `.xlsx` name; it is read with the
  `calamine` engine (`python-calamine`), which pandas recommends over the deprecated `xlrd`.
- Monitor metrics generalised from "chokepoint" to "location", so ports reuse them unchanged.
- App structure: one module per tab in `src/ptf/app/tabs/` with `layout(data)`,
  `update(...)` (plain, tested function) and `register(app, state)`; shared figures in
  `charts.py`, colours in `style.py`. Tabs whose data are missing show a hint instead of
  failing.
- Charts: fixed x-range per selected period (Plotly would otherwise widen the axis for
  annotation text), indexed series instead of dual axes, colours tied to the series and
  not to their position among the visible ones.

**Consequences.** Scenario models (SPEC section 5) are postponed; the dashboard data (Red
Sea diversion, Hormuz, gas spread, freight index) are the planned inputs for them.

---

## ADR-008: Trade flows tab from the PortWatch port network

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** Flows of goods between large ports, split by cargo type, were requested. No free
source combines both: PortWatch has a port-to-port network (all vessel types) and daily
country trade by vessel type (no partner).

**Decision.**
- Show both side by side in a "Trade flows" tab: a flow map of the port network and the
  cargo mix of a country over time, plus a ranking of countries per cargo type.
- Long-haul links (international, 5+ days) by default; short feeder services dominate the
  network otherwise.
- Network download once (static snapshot), links above 1,000 t/day only.
- Country trade download opt-in (`download_country_trade: false`): 560,000 rows at 2–3.5 s
  per page of 1,000 rows take 20–25 minutes the first time. Without it, the tab shows the
  network and a hint how to enable the cargo section.
- Flow lines are drawn as one Plotly trace per width class (four quartiles) with
  `None`-separated segments, plus invisible midpoint markers for the hover text: hundreds of
  single-line traces would make the map slow.

**Consequences.** Commodity flows between countries by product (crude oil, LNG, iron ore,
polyethylene) would need CEPII BACI, a later step.

---

## ADR-009: CEPII BACI replaces our own Comtrade download as trade source

- **Date:** 2026-11-13
- **Status:** accepted; supersedes the Comtrade parts of ADR-003 and ADR-004

**Context.** The public Comtrade endpoint allows about 100 requests a day (ADR-003). After
two days, 17 of 30 reporters were loaded and Asia and Africa were missing, so the model
underestimated demand in Asia (China 5.5 instead of ~13–14 Mt of imports). Our own mirror
reconciliation worked but is exactly what CEPII publishes in BACI, for all ~200 countries.

**Decision.**
- Trade data come from **CEPII BACI**, version 202601, HS 2017 revision (years 2017–2024),
  one ~800 MB zip downloaded once to `data/raw/baci/` (licence Etalab 2.0, no registration).
  The zip is kept: other products (crude oil, LNG, iron ore) can be extracted later.
- The clean step reads the yearly CSVs in chunks directly from the zip, keeps HS 3901xx and
  writes `trade_hs6` (one row per product flow) and `bilateral_flows` (summed per
  relation, the input of the model). Missing quantities are imputed as value / median unit
  value of the same HS6 product and year and flagged.
- BACI values are FOB (CEPII removes estimated freight and insurance from import values).
- Our Comtrade pipeline stays in the code as a **check**, not part of `pipeline all`:
  `pipeline comtrade` writes `trade_reports`, `mirror` and `comtrade_flows`, and the
  data-quality report then compares our reconciliation with BACI.

**Consequences.** Complete, consistent trade data without API limits, plus the split by
polyethylene type (HS6). BACI is published once a year (latest data: 2024); the most recent
months are not covered, which is what the PortWatch-based dashboard is for.

---

## ADR-010: Working agreement and quality gates for AI-assisted development

- **Date:** 2026-11-13
- **Status:** accepted

**Context.** Most of the code is generated with an AI assistant. Until v0.3.0 all 51 commits
went straight to `main`, type hints were written but never checked (63 mypy errors), and test
modules imported each other. That is fast, but nothing stops a plausible-looking mistake.

**Decision.**
- **Spec → branch → PR → review → merge.** Every change gets a short feature spec in
  `specs/` with acceptance criteria that become tests; `SPEC.md` stays the overall
  specification. No direct commits to `main`; versions are tagged after each phase and
  recorded in `CHANGELOG.md`.
- **Automatic gates in CI and pre-commit:** ruff (lint and format), mypy in strict mode, tests
  with at least 85 % coverage. The Definition of Done in `CLAUDE.md` and the PR template
  list the same checks.
- **mypy strict except `warn_return_any`:** many pandas methods return `Any` in the stubs;
  flagging each return adds noise without finding bugs. Libraries without type information
  (Pyomo, searoute, Plotly, HiGHS) are imported as `Any`.
- Rows of DataFrames are read with `to_dict("records")` where values are passed on; optional
  tables in the app are narrowed with `require()`.

**Consequences.** Every change leaves a reviewable trail (spec, PR, CI run). Next
architecture steps, each as its own spec and PR: data model in DuckDB/dbt (ADR to follow),
package structure by domain, Docker, Airflow, run metadata.

---

## ADR-011: Data model and transformations in SQL with dbt on DuckDB

- **Date:** 2026-11-13
- **Status:** accepted (2026-11-13, option A)

**Context.** Since v0.3.0 the clean layer consists of 13 loose Parquet files written by
pandas functions (`ptf.clean.*`). Their schema lives in Python constants and in a hand-written
data dictionary that a test keeps in sync. This works, but:

- the **data model is implicit**: countries, regions, products, ports and chokepoints appear
  as repeated text columns in many tables; there are no dimension tables, no keys and no
  checked relationships between tables;
- **transformations are hidden in Python** (filters, joins, aggregations, imputation), although
  most of them are set operations that SQL expresses more directly and that analysts can read;
- **data checks are limited** to column names; types, uniqueness, missing values and valid
  references are not checked;
- SQL is used in only two places (DuckDB in the data-quality report).

**Options.**

| | A. dbt + DuckDB | B. SQLMesh + DuckDB | C. own SQL runner + pandera | D. pandas + pandera (status quo) |
|---|---|---|---|---|
| Transformations | SQL models (+ Jinja), dependency graph from `ref()` | SQL/Python models, column-level lineage | SQL files run in order by our code | Python functions |
| Data tests | built in (unique, not_null, relationships, accepted_values, custom) | built in (audits) | pandera schemas | pandera schemas |
| Documentation / lineage | `dbt docs`: model graph and column descriptions from YAML | built-in UI | own | own (data dictionary) |
| Spread in industry | standard for analytics engineering | growing, smaller | – | standard for pandas |
| Risk | dbt v2 (Rust engine) in transition; Python dbt-core 1.x and dbt-duckdb remain maintained and Apache-2.0 | owned by Fivetran since 2025 (merged with dbt Labs); open source today, direction unclear | we maintain a mini-dbt | data model stays implicit |
| Extra tooling | dbt project, `profiles.yml`, Jinja | SQLMesh project, state | little | little |

**Decision: A – dbt-core 1.x with the dbt-duckdb adapter, one DuckDB file as
warehouse.**

- **Division of labour:**
  - *Python* does what needs Python: downloads (APIs, zip), unpacking the BACI zip to a
    Parquet landing file, the LP (Pyomo), the app (Dash).
  - *dbt/SQL* does every transformation from raw files to analysis tables.
- **Layers in `data/warehouse.duckdb`:**
  - `raw` stays files on disk (sources in dbt, immutable as before);
  - `staging` (`stg_*`): one model per source, renamed, typed, deduplicated – no business
    logic;
  - `marts`: a **star schema** – dimensions `dim_country`, `dim_region`, `dim_product`,
    `dim_port`, `dim_chokepoint`, `dim_date`; facts `fct_trade` (year × exporter × importer ×
    HS6), `fct_chokepoint_transits` (day × chokepoint), `fct_port_activity` (day × port),
    `fct_market_prices` (date × series); derived marts for consumers, e.g.
    `mart_region_trade` for the LP and `mart_monitor_*` for the app.
- **Configuration stays in YAML:** a small Python step writes `config/regions.yaml` as a
  reference table that dbt reads; assumptions do not move into SQL.
- **Tests:** dbt tests on every mart (keys unique and not null, relationships to dimensions,
  accepted values, quantities ≥ 0) run in CI with `dbt build` on the fixture data.
- **Documentation:** column descriptions in dbt YAML replace the hand-written data
  dictionary for the warehouse tables; `dbt docs` shows the lineage.
- **Pin versions** (`dbt-core`, `dbt-duckdb`, `duckdb`) and keep to plain SQL with little
  Jinja, so that a later move to dbt v2 stays simple.
- **Migration in small PRs**, each with a parity test (new mart equals the old pandas table
  within tolerance) before the pandas function is removed: trade (BACI) first, then
  PortWatch and markets, then the app reads marts instead of Parquet files.
- The **monitor metrics** (rolling means, seasonal baseline) stay in Python for now; moving
  them to SQL window functions is a separate later decision. The Comtrade check stays in
  Python as legacy.

**Consequences.**
- *Positive:* explicit, tested data model; transformations readable as SQL; lineage and docs
  generated; a clear seam for Airflow (`dbt build` as one task); the LP and the app read
  from one database instead of many files.
- *Negative:* a second toolchain (dbt, Jinja, profiles); the move takes several PRs; during
  the migration both paths exist side by side.
- *To check during the first PR:* compatibility of dbt-duckdb with DuckDB 2.0 and dbt-core
  1.12; reading Parquet sources from DuckDB without extra extensions.

## ADR-012: Package structure by domain with enforced dependency rules

- **Date:** 2026-11-13
- **Status:** accepted (spec 004)

**Context.** The package grew in two directions at once: phase 1 sliced it by technical
layer (`ingest/`, `clean/`), the dashboard by topic (`monitor/`, `market/`, `model/`).
Configuration modules lay scattered at the top level (`market_config.py`,
`pipeline_config.py`, `regions.py`), the superseded Comtrade code sat in the core package,
and `pipeline.py` imported 17 modules. After the move to dbt (ADR-011) `clean/` held mostly
legacy code. A change to the market data touched five places; every new source made the
central pipeline longer.

**Options.**
- *A. Slice by layer* (`ingest/`, `transform/`, `report/`): familiar, but things that change
  together lie apart, and the transformations now live in dbt anyway.
- *B. Slice by domain* (`trade`, `shipping`, `markets`, `model`) on top of a shared `core`:
  the same cut as the dbt project and the later Airflow DAGs.
- *C. Leave as is*: no work, but the mix keeps growing.

**Decision: B.**
- `ptf.core`: settings, HTTP retries, the warehouse (running dbt, reading marts), shared
  reference data (`regions.yaml`) and Markdown helpers. It imports no other `ptf` package.
- One package per domain with its downloads, its `config.py` (reading `config/<domain>.yaml`),
  its logic and a `steps.py` whose functions take only `Settings`.
- **Domains do not import each other.** Data of another domain come from the warehouse (the
  LP reads `marts.mart_region_trade`, not `ptf.trade`). The warehouse is the interface.
- `ptf.legacy.comtrade` holds the superseded Comtrade check; only the command line uses it.
- `ptf.cli` is the only module that knows every domain: a registry from step names to step
  functions (`uv run ptf <step>`); argparse is enough, no extra CLI framework.
- The rules are checked by **import-linter** (`uv run lint-imports`, CI and pre-commit):
  a layers contract (`cli | app` → domains → `core`, domains independent) and a forbidden
  contract (`app` must not import `legacy`).

**Consequences.**
- *Positive:* a change to one source stays in one package (plus its dbt folder); the code,
  `config/` and dbt use the same domain names; Airflow (phase 5) can run one DAG per domain
  that calls its `steps.py`; legacy code can be deleted without side effects.
- *Negative:* one large move (many paths changed, `git log --follow` needed for history);
  `regions.yaml` is shared reference data in `core`, a deliberate exception to "core has no
  domain content".

## ADR-013: Docker image with uv in two stages, data on volumes

- **Date:** 2026-11-13
- **Status:** accepted (spec 005)

**Context.** The project ran only where Python 3.12, uv and the locked packages were set up
by hand. Airflow (step 5) and any server need the same environment again. The code also
held assumptions about the machine: the app listened on `127.0.0.1` only, the dbt project
was found relative to the source file, and dbt wrote `target/` and `logs/` into the project.

**Decision.**
- **One image, two stages.** *builder* (`python:3.12-slim` + the uv binary, same version as
  locally) runs `uv sync --locked --no-dev`, first without the project (a layer that changes
  only with `uv.lock`), then with it, non-editable. *runtime* (`python:3.12-slim`) receives
  only `.venv`, `config/` and `dbt/`: no uv, no compilers, no tests.
- **Data and secrets stay outside.** `.dockerignore` keeps out `data/`, `.env`, `.git`,
  tests and docs; `compose.yaml` mounts `./data` (and `./docs` for the pipeline's reports)
  and passes `.env` optionally via `env_file`.
- **Settings instead of machine assumptions:** `APP_HOST`/`APP_PORT` (container:
  `0.0.0.0:8050`), `DBT_PROJECT_DIR` (container: `/app/dbt`); dbt output to `/tmp` via
  `DBT_TARGET_PATH`/`DBT_LOG_PATH`, so the dbt folder can stay read-only.
- **Non-root user** `ptf`; port published on `127.0.0.1` of the host only.
- **gunicorn** serves the app in the container (`ptf.app.wsgi:server`) instead of Flask's
  development server: one worker (the app holds its data in memory, `AppState`), four
  threads. Locally `python -m ptf.app` is unchanged.
- **Without a warehouse** the app shows a start page with the commands to run instead of
  failing; this lets CI check the image without data and helps a fresh clone.
- **CI** builds the image and runs `docker/smoke_test.sh`: no data/`.env`/uv in the image,
  user `ptf`, `ptf --help`, app healthy. No registry push yet.

**Consequences.**
- *Positive:* the same environment locally, in CI and later in Airflow; pipeline steps run
  as `docker compose run --rm pipeline <step>` with identical results (LP 2023: 42 %).
- *Negative / to know:*
  - The image is **1.06 GB**, ~930 MB of it Python packages (pyarrow 155 MB, pandas,
    plotly, duckdb, pyomo, dash). Fine for now; slimming would mean splitting the image
    (app without Pyomo/dbt), which is not worth it yet.
  - Charts rendered in the container use Linux fonts, so the PNGs in `docs/figures` differ
    in bytes from those rendered on the Mac; the numbers are the same.
  - Files written to `./data` belong to the host user on macOS (Docker Desktop maps them);
    on Linux the container user's id (system user) would own them; set `user:` in compose
    there if needed.
  - The Mac builds `linux/arm64`, CI `linux/amd64`; all dependencies ship wheels for both.

## ADR-014: Insights layer for logic that combines domains

- **Date:** 2026-11-13
- **Status:** accepted (spec 006)

**Context.** The buyer view needs numbers that no single domain can compute: the share of
Europe's imports that passes a disrupted chokepoint combines trade (who supplies), model
(which sea route) and shipping (which chokepoint is disrupted). ADR-012 forbids domains to
import each other, and the app must not hold business logic.

**Options.**
- *A. Put it in the app:* quick, but logic in Dash callbacks is hard to test and reuse.
- *B. Let one domain import the others* (e.g. shipping imports trade): breaks ADR-012 and
  creates hidden coupling.
- *C. Compute it in dbt:* the disruption flag comes from Python (rolling seasonal baseline,
  section 4.2 of the methodology); moving it to SQL is a larger, separate decision.
- *D. A new layer `ptf.insights` between the entry points and the domains.*

**Decision: D.** `ptf.insights` may import any domain and `core`; domains must not import
it; the app and the CLI may. import-linter enforces the new layer order
`cli | app` → `insights` → domains → `core`, and `insights` must not use `legacy`.
`insights.view` computes everything a buyer tab shows from the loaded tables, so the tabs
only format and draw.

**Consequences.**
- *Positive:* cross-domain questions have a tested home with plain functions and
  hand-checkable unit tests; domains stay independent.
- *Negative:* one more layer to understand; the line between "domain logic" and "insight"
  needs judgement (rule: if it needs two domains, it is an insight).

## ADR-015: Unofficial Asian price source behind an optional dependency

- **Date:** 2026-11-14
- **Status:** accepted (spec 011, user decision: option A)

**Context.** The only free near-real-time polyethylene price is the LLDPE future of the
Dalian Commodity Exchange. The exchange blocks automated access (HTTP 412); the price is
available through Sina Finance, which the open-source library AKShare reads. AKShare is MIT
licensed and widely used, but by its own statement "just for academic research purpose",
its interfaces "may be removed", it releases very often and brings a V8 JavaScript engine
(`mini-racer`) and browser-imitating requests (`curl_cffi`) with about 160 packages in total.

**Options.** A. AKShare as an optional dependency; B. own `requests` call of the Sina
endpoint (smaller attack surface, but we maintain the parser); C. no Asian price.

**Decision: A, isolated.**
- `[project.optional-dependencies] asia = ["akshare==1.20.42"]`: exact version, hashes in
  `uv.lock`; updates only deliberately after reading the changelog.
- The core pipeline, the tests and the Docker image do not need it; `ptf market` downloads
  the price only when AKShare can be imported, and a failing source logs a warning.
- Raw files are kept, so stored prices survive a broken source; the landing is always
  written so dbt builds.
- Tests replace AKShare with a fake; a separate CI job runs the DCE tests with the extra and
  `pip-audit` over all its packages (no known vulnerabilities on 2026-11-14).
- The price is shown as an indicator with a visible "unofficial" note; it does not feed the
  landed cost or the order planner.

**Consequences.** A daily Asian PE price at low cost. Risks: the source can change or
disappear (then switch to option B or drop it); third-party code runs in the download step.
Since spec 012 that step (`ptf dce`) runs in Docker in its own container `asia` (image
`ptf:asia` with the extra): only `data/raw/dce` mounted, no `.env`, read-only file system,
no Linux capabilities, `no-new-privileges`; the marts are built afterwards by the normal
pipeline container without AKShare (least privilege). Open for hosting: restricting the
container's network to Sina's hosts (needs a proxy) and polling during trading hours. To remove
it: delete the `asia` extra, `ptf.markets.dce`, the `dce` block in `config/markets.yaml`,
the dbt staging model and the chart.

## ADR-016: Only sourced values

- **Date:** 2026-11-14
- **Status:** accepted (spec 015, user rule "nur Daten, die durch die Datenquellen bestätigt
  sind, ohne Ausnahme")

**Context.** The configs held estimates labelled `source: assumption`: freight per tonne,
ship speed, port days, buffers, overland days, LP capacities, utilisation and costs. Shown
in a dashboard next to measured data, they look just as reliable, and some were invented
for the occasion (a rail cost for Uzbekistan, a 50/50 port split for Saudi Arabia).

**Options.** A. keep estimates, labelled; B. only sourced values, missing ones shown as
"n/a"; C. estimates as ranges.

**Decision: B.**
- Facts in `config/` are `{value, source, url, read}` (`ptf.core.sourced.Sourced`,
  `SourcedTable`, `SourcedRate` with validity); they do not load without source, url and date.
- Settings (thresholds, windows, years, the representative port of a region) are plain
  numbers and named as settings.
- `docs/value_register.md` lists every config number with its class; a test checks it is
  complete and current. A second test rejects numbers with units in app texts.
- Views degrade instead of estimating: landed cost without freight is "price + duty, excl.
  freight"; the planner shows ship transit time from sourced parts and recommends nothing
  without freight; the transport LP is switched off (`enabled: false`) while inputs are
  missing, and refuses to be switched on until they are sourced.
- Tests that need the LP use a synthetic config marked as a test fixture.

**Consequences.** Fewer numbers, each traceable. Landed cost and the planner lose freight
and part of the lead time until a free freight source is found (phase 5); the LP stays off.
Static values carry a read date and go stale: tariff preferences expire (several on
31 Dec 2026) and are applied only inside their validity.
