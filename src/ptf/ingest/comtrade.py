"""Download annual bilateral trade data from the public UN Comtrade API into the raw layer.

The public preview endpoint needs no key but returns at most 500 records and one period per
request and throttles to roughly one request per second (see ADR-003). Therefore we:

1. request one reporter and one year at a time,
2. pause between requests and retry with exponential backoff on HTTP 429 / 5xx,
3. cache every response as its own Parquet file, so each request runs only once.

Raw files hold the API records unchanged plus a `fetched_at` timestamp.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DATA_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
REFERENCE_URL = "https://comtradeapi.un.org/files/v1/app/reference/{name}.json"

# The preview endpoint silently truncates at this many records.
MAX_RECORDS = 500

# Status codes worth retrying: throttling and temporary server errors.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

Sleep = Callable[[float], None]


def build_params(reporter_code: int, year: int, hs_code: str, flow_codes: str) -> dict:
    """Query parameters for one reporter, one year and one HS code.

    `partner2Code=0`, `customsCode=C00` and `motCode=0` ask for totals only (no breakdown by
    second partner, customs procedure or mode of transport), so each reporter-partner-flow
    combination appears exactly once.
    """
    return {
        "reporterCode": reporter_code,
        "period": year,
        "cmdCode": hs_code,
        "flowCode": flow_codes,
        "partner2Code": 0,
        "customsCode": "C00",
        "motCode": 0,
    }


def get_json(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    max_retries: int = 5,
    base_wait_seconds: float = 2.0,
    sleep: Sleep = time.sleep,
) -> dict:
    """GET a JSON document; on throttling or server errors wait 2, 4, 8, ... seconds and retry."""
    for attempt in range(max_retries + 1):
        response = session.get(url, params=params, timeout=60)
        if response.status_code not in RETRYABLE_STATUS:
            response.raise_for_status()  # other 4xx errors are bugs, not worth retrying
            return response.json()

        if attempt == max_retries:
            response.raise_for_status()
        wait = base_wait_seconds * 2**attempt
        logger.warning("HTTP %s for %s, retrying in %.0f s", response.status_code, url, wait)
        sleep(wait)

    raise AssertionError("unreachable")  # the loop either returns or raises


def fetch_reporter_year(
    session: requests.Session,
    reporter_code: int,
    year: int,
    hs_code: str,
    max_retries: int = 5,
    sleep: Sleep = time.sleep,
) -> pd.DataFrame:
    """Fetch imports and exports of one reporter in one year as a DataFrame of raw records."""
    records = _fetch_records(session, reporter_code, year, hs_code, "M,X", max_retries, sleep)

    if len(records) >= MAX_RECORDS:
        # Response may be truncated: split by flow so each request stays below the limit.
        logger.info(
            "Reporter %s %s hit %s records, splitting by flow", reporter_code, year, MAX_RECORDS
        )
        records = []
        for flow in ("M", "X"):
            part = _fetch_records(session, reporter_code, year, hs_code, flow, max_retries, sleep)
            if len(part) >= MAX_RECORDS:
                raise RuntimeError(f"reporter {reporter_code} {year} {flow}: still truncated")
            records.extend(part)

    raw = pd.DataFrame(records)
    raw["fetched_at"] = datetime.now(UTC)
    return raw


def _fetch_records(
    session: requests.Session,
    reporter_code: int,
    year: int,
    hs_code: str,
    flow_codes: str,
    max_retries: int,
    sleep: Sleep,
) -> list[dict]:
    params = build_params(reporter_code, year, hs_code, flow_codes)
    payload = get_json(session, DATA_URL, params, max_retries=max_retries, sleep=sleep)
    if payload.get("error"):
        raise RuntimeError(f"Comtrade error for {params}: {payload['error']}")
    return payload.get("data") or []


def raw_path(raw_dir: Path, reporter_iso3: str, year: int) -> Path:
    return raw_dir / "comtrade" / f"{reporter_iso3}_{year}.parquet"


def ingest_comtrade(
    reporters: dict[str, int],
    years: list[int],
    hs_code: str,
    raw_dir: Path,
    session: requests.Session | None = None,
    pause_seconds: float = 1.5,
    max_retries: int = 5,
    sleep: Sleep = time.sleep,
) -> list[Path]:
    """Download all reporter-year combinations that are not cached yet.

    `reporters` maps ISO3 codes to Comtrade reporter codes. Cached files are never refetched;
    delete a file to refresh it (e.g. when a country publishes a late year).
    An empty response (country has not reported that year) is cached as an empty file too.
    """
    session = session or requests.Session()
    written: list[Path] = []
    for iso3, code in reporters.items():
        for year in years:
            path = raw_path(raw_dir, iso3, year)
            if path.exists():
                logger.debug("cached: %s", path)
                continue

            raw = fetch_reporter_year(session, code, year, hs_code, max_retries, sleep)
            path.parent.mkdir(parents=True, exist_ok=True)
            raw.to_parquet(path, index=False)
            written.append(path)
            logger.info("%s %s: %s records -> %s", iso3, year, len(raw), path)
            sleep(pause_seconds)  # be polite: the public endpoint throttles hard
    return written


def ingest_reference(
    name: str, raw_dir: Path, session: requests.Session | None = None, sleep: Sleep = time.sleep
) -> Path:
    """Cache a Comtrade reference table (e.g. `partnerAreas`, `Reporters`) as Parquet."""
    path = raw_dir / "comtrade_reference" / f"{name}.parquet"
    if path.exists():
        return path
    session = session or requests.Session()
    payload = get_json(session, REFERENCE_URL.format(name=name), sleep=sleep)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(payload["results"]).to_parquet(path, index=False)
    return path


def reporter_codes(reporters_reference: pd.DataFrame, iso3_codes: list[str]) -> dict[str, int]:
    """Map ISO3 codes to current Comtrade reporter codes.

    Historic entries (e.g. West Germany, code 280) carry an `entryExpiredDate` and are skipped.
    Countries that do not report to Comtrade at all (e.g. Taiwan) are left out with a warning;
    their trade is still visible through their partners' reports (mirror statistics).
    """
    current = reporters_reference
    if "entryExpiredDate" in current.columns:
        current = current[current["entryExpiredDate"].isna()]
    lookup = dict(zip(current["reporterCodeIsoAlpha3"], current["reporterCode"], strict=True))

    codes: dict[str, int] = {}
    for iso3 in iso3_codes:
        if iso3 in lookup:
            codes[iso3] = int(lookup[iso3])
        else:
            logger.warning("%s is not a Comtrade reporter; only mirror data will exist", iso3)
    return codes
