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
