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
