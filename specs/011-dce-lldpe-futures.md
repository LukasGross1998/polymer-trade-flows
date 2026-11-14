# 011 – Daily LLDPE price from the Dalian futures exchange (AKShare)

- **Status:** done
- **Branch / PR:** `feat/dce-futures` / see PR
- **SPEC.md sections:** 7 (app), 10 (next steps); decision on 2026-11-14: option A of spec 010
- **ADR:** ADR-015 (unofficial data source behind an optional dependency)

## Goal

A daily, exchange-based polyethylene price as an additional signal: the LLDPE main
contract of the Dalian Commodity Exchange (DCE, China, CNY/t), in USD and EUR on the Prices
tab. It is the only free near-real-time PE price; it shows the mood in Asia, not the
European contract price, and is never used as the basis of a recommendation.

## Acceptance criteria

1. **Optional dependency:** AKShare is installed only with `uv sync --extra asia`
   (`[project.optional-dependencies] asia = ["akshare==<pinned version>"]`). The exact
   version is pinned; `uv.lock` holds the hashes. Without the extra, the app, the tests and
   the Docker image work unchanged; the Prices tab then says "DCE price not installed".

2. **Download** (`ptf.markets.dce`): `ptf market` calls AKShare's Sina-based daily function
   for the LLDPE main contract (symbol `L0`; the exact function is checked on the first run
   and documented), only if AKShare can be imported. Raw layer: one Parquet per download in
   `data/raw/dce/`, never overwritten; failures (source changed, network, blocked) are
   logged as a warning and do not stop the market step. The import of AKShare happens
   inside the function, so the module loads without it.

3. **Warehouse:** the series `DCE_LLDPE` (CNY/t, daily, group `freight_polymers`) joins
   `marts.mart_market_series` via a dbt staging model (latest download per day); dbt tests
   as for the FRED series. Before the first download an empty landing file keeps dbt
   building (as for the GSCPI).

4. **Prices tab:** a chart "LLDPE futures, Dalian (main contract)" in CNY/t and converted to
   USD (FRED `DEXCHUS`) and EUR (`DEXUSEU`), with the period selector; a KPI "DCE LLDPE,
   USD/t" with the 30-day change; a visible source note "Sina Finance via AKShare –
   unofficial, for research; prices in China incl. VAT, not comparable 1:1 with export
   prices".

5. **Tests:** AKShare is replaced by a fake in all tests (no network, no AKShare needed in
   CI): download with the fake (two days), skip when AKShare is missing, failure tolerance,
   conversion example (8,000 CNY/t at 7.20 CNY/USD = 1,111.11 USD/t), mart content.

6. **Isolation and checks:**
   - the market step can run in its own container without `.env` (no keys needed), see
     README "Run with Docker";
   - `pip-audit` (known vulnerabilities of the installed packages) as a CI step for the
     `asia` extra in a separate job, so a finding does not block the core pipeline;
   - ADR-015 records why an unofficial source behind an optional dependency is acceptable
     here, and how to remove it.

7. Quality gates as usual; source and caveats in `docs/methodology.md` and the README table
   "Data sources and keys".

## Out of scope

- Other Chinese contracts (PP, PVC, ethylene glycol), intraday prices, the futures curve.
- Using the DCE price in the landed cost or the order planner.
- Option B (own Sina call) – kept as the fallback if AKShare breaks or is withdrawn.

## Design notes

- AKShare facts (checked 2026-11-14 on PyPI, GitHub, docs): MIT licence, about 23k GitHub
  stars, very frequent releases, Python ≥ 3.11.5; dependencies include `mini-racer` (V8
  JavaScript engine) and `curl_cffi` (browser-like requests); its own statement: "just for
  academic research purpose", interfaces "may be removed". Direct DCE access is blocked by
  the exchange (HTTP 412); the Sina route works per the docs.
- The installation of AKShare needs your approval in this session (a test install was
  blocked by the permission check); it is added with `uv add --optional asia akshare==…`.
- Files: `pyproject.toml`, `uv.lock`, `src/ptf/markets/{dce,steps}.py`,
  `dbt/models/staging/markets/stg_dce__lldpe.sql`, the market mart, `config/markets.yaml`,
  `src/ptf/app/tabs/prices.py`, `.github/workflows/ci.yml`, tests, docs.
- Implemented: function `akshare.futures_main_sina(symbol="L0", ...)` (checked on the first
  run, 208 trading days in 2026, 8,578 CNY/t on 13 Nov); AKShare 1.20.42 pinned; `pip-audit`
  over the 160 packages of the extra: no known vulnerabilities. The series gets its own
  group `china_futures`, so the EUR switch does not treat CNY prices as USD.
- Deviation: AKShare is not in the Docker image (the image is built without extras), so the
  DCE download runs locally; running it in its own container without secrets is noted in
  ADR-015 for the hosting phase.
