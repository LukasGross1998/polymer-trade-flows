# 012 – Isolated container for the AKShare download, latest intraday quote

- **Status:** done
- **Branch / PR:** `feat/asia-container` / see PR
- **SPEC.md sections:** 9 (architecture), 10 (next steps); follows spec 011 and ADR-015

## Goal

The third-party code of AKShare runs only where it is needed, with as few rights as
possible: in its own short-lived container that sees nothing but the Dalian raw folder and
no secrets. The app and the normal pipeline stay without AKShare. In addition, each
download stores the latest intraday quote, so a run during the Dalian trading hours shows
the current price next to yesterday's close.

## Acceptance criteria

1. **Own pipeline step `ptf dce`** (`markets.steps.download_dce`): downloads the daily
   history and the latest quote and writes the landing files – no dbt, no other source.
   `ptf market` keeps working as before (with AKShare locally it downloads too; without it
   only the landing files are written and dbt builds).

2. **Second image from the same Dockerfile:** build argument `EXTRAS` (default empty),
   used in both `uv sync` calls. `ptf:local` stays as it is; `ptf:asia` is built with
   `EXTRAS="--extra asia"`.

3. **Compose service `asia`** (profile `asia`, started only on request:
   `docker compose run --rm asia`):
   - image `ptf:asia`, command `ptf dce`;
   - **only** `./data/raw/dce` mounted (read-write), no `env_file`, so no keys reach it;
   - hardening: read-only root file system with a small `/tmp`, all Linux capabilities
     dropped, `no-new-privileges`, non-root user (as all our images).
   Then `docker compose run --rm pipeline market` builds the marts from the new landing
   file without AKShare.

4. **Latest intraday quote** (`ptf.markets.dce`): AKShare's real-time quote of the LLDPE
   contracts (`futures_zh_realtime`), the row of the main contract `L0`: last trade, bid,
   ask, previous settlement, time of the download. Raw file per download; landing
   `dce/landing_dce_quote.parquet` (newest quote, empty before the first); dbt staging and
   `marts.mart_dce_quote` (one row). A failing quote does not stop the daily download.
   Tests with a fake answer in AKShare's column format.

5. **Prices tab:** next to the daily close a line "latest quote 8,547 CNY/t (bid 8,547 /
   ask 8,551), fetched Fri 13 Nov 15:58 CET" when the quote is newer than the last daily
   close; trading hours of Dalian in CET as a note (02:00–04:30, 06:30–08:00, 14:00–16:00
   in winter).

6. **CI:** the Docker job also builds `ptf:asia` and checks inside it that AKShare can be
   imported, that `ptf dce` is a known step, and that the container cannot write outside
   the mounted folder (read-only root file system).

7. README "Run with Docker" and ADR-015 updated (the isolation is built, no longer only
   planned); quality gates as usual.

## Out of scope

- Polling every few minutes (a permanently running worker) – hosting phase, noted.
- Minute bars (`futures_zh_minute_sina`); other contracts.
- Network restrictions (allowing only Sina's hosts) – would need a proxy; noted for
  hosting.

## Design notes

- Checked on 2026-11-14 (Saturday, exchange closed): `futures_zh_realtime("塑料")` returns
  the LLDPE contracts with columns `symbol, exchange, name, trade, settlement,
  presettlement, open, high, low, close, bidprice1, askprice1, bidvol1, askvol1, ...`; L0
  last trade 8,547 CNY/t, bid 8,547 / ask 8,551 (Friday night session). How fresh Sina's
  quote is during trading (real time or delayed) is not documented; the tab shows the
  download time, not a claimed trade time.
- Why only the raw folder is mounted: if AKShare or one of its 160 packages did something
  unexpected, it could at most write into `data/raw/dce` – not the warehouse, the other raw
  data, `.env` or the code. The dbt build that reads the landing file runs in the normal
  pipeline container without AKShare.
- Files: `Dockerfile`, `compose.yaml`, `docker/smoke_test.sh`, `.github/workflows/ci.yml`,
  `src/ptf/{cli.py,markets/dce.py,markets/steps.py}`, `dbt/models/staging/markets/
  stg_dce__quote.sql`, `dbt/models/marts/markets/mart_dce_quote.sql`,
  `src/ptf/app/tabs/prices.py`, tests, README, `docs/decisions.md`.
- Implemented and checked with real data on 2026-11-14: `docker compose run --rm asia`
  downloaded 1,906 days and the quote (L0 8,547 CNY/t, bid 8,547 / ask 8,551, last trade
  23:00 Beijing, trading day 16 Nov) into `data/raw/dce`; `docker compose run --rm pipeline
  market` (without AKShare) built the marts. Image sizes: `ptf:local` 1.06 GB, `ptf:asia`
  1.21 GB. Found while testing: AKShare's real-time answer also has empty columns `bid`
  and `ask`, which clashed with the renamed `bidprice1`/`askprice1` – fixed (select, then
  rename) and added to the test fake.
