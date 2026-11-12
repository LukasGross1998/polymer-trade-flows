"""Download daily chokepoint transits from IMF PortWatch (ArcGIS REST API, no key).

- `Daily_Chokepoints_Data`: one row per day and chokepoint, vessel counts by type and
  capacity (deadweight tonnage), from 2019-01-01. Updated roughly weekly, a few days behind.
- `PortWatch_chokepoints_database`: chokepoint names and coordinates for the map.

The API returns at most 1,000 rows per request, so queries are paged with `resultOffset`.
Updates are incremental: only days from (last stored date - revision_days) are requested,
because PortWatch revises recent days. Every download is its own raw file and is never
overwritten; the clean step keeps the latest value per day.
"""

import logging
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from ptf.ingest.http import Sleep, get_json

logger = logging.getLogger(__name__)

SERVICES = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
DAILY_URL = f"{SERVICES}/Daily_Chokepoints_Data/FeatureServer/0/query"
CHOKEPOINTS_URL = f"{SERVICES}/PortWatch_chokepoints_database/FeatureServer/0/query"
PAGE_SIZE = 1000


def query_all(
    session: requests.Session,
    url: str,
    where: str,
    out_fields: str,
    order_by: str,
    sleep: Sleep = time.sleep,
) -> list[dict]:
    """Run an ArcGIS query page by page and return the attribute rows of all features.

    ArcGIS sets `exceededTransferLimit: true` while more rows are available.
    """
    rows: list[dict] = []
    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "orderByFields": order_by,  # a stable order is required for paging
            "resultOffset": len(rows),
            "resultRecordCount": PAGE_SIZE,
            "returnGeometry": "false",
            "f": "json",
        }
        payload = get_json(session, url, params, sleep=sleep)
        if "error" in payload:
            raise RuntimeError(f"PortWatch error: {payload['error']}")
        features = payload.get("features", [])
        rows.extend(feature["attributes"] for feature in features)
        if not payload.get("exceededTransferLimit") or not features:
            return rows


def daily_dir(raw_dir: Path) -> Path:
    return raw_dir / "portwatch" / "chokepoints_daily"


def last_stored_date(raw_dir: Path) -> date | None:
    """Latest day in all raw daily files, or None before the first download."""
    files = sorted(daily_dir(raw_dir).glob("*.parquet"))
    if not files:
        return None
    dates = pd.concat(pd.read_parquet(f, columns=["date"]) for f in files)["date"]
    return pd.to_datetime(dates).max().date() if len(dates) else None


def ingest_chokepoint_transits(
    raw_dir: Path,
    revision_days: int = 14,
    session: requests.Session | None = None,
    sleep: Sleep = time.sleep,
) -> Path | None:
    """Fetch new (and recently revised) days; returns the new raw file or None if nothing new."""
    session = session or requests.Session()
    last = last_stored_date(raw_dir)
    if last is None:
        where = "1=1"
    else:
        since = last - timedelta(days=revision_days)
        where = f"date >= DATE '{since.isoformat()}'"

    rows = query_all(session, DAILY_URL, where, "*", "date,portid", sleep)
    if not rows:
        logger.info("PortWatch: no rows for %s", where)
        return None

    raw = pd.DataFrame(rows)
    fetched_at = datetime.now(UTC)
    raw["fetched_at"] = fetched_at
    # Microseconds in the name: two downloads in the same second must not share a file.
    path = daily_dir(raw_dir) / f"{fetched_at:%Y%m%dT%H%M%S%f}.parquet"
    if path.exists():
        raise FileExistsError(f"raw files are never overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(path, index=False)
    logger.info("PortWatch: %s rows (%s) -> %s", len(raw), where, path)
    return path


def ingest_chokepoints(
    raw_dir: Path, session: requests.Session | None = None, sleep: Sleep = time.sleep
) -> Path:
    """Cache the chokepoint reference table (names, coordinates) once."""
    path = raw_dir / "portwatch" / "chokepoints.parquet"
    if path.exists():
        return path
    session = session or requests.Session()
    rows = query_all(session, CHOKEPOINTS_URL, "1=1", "*", "portid", sleep)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path
