"""Download IMF PortWatch data (ArcGIS REST API, no key).

- `Daily_Chokepoints_Data`: one row per day and chokepoint, vessel counts by type and
  capacity (deadweight tonnage), from 2019-01-01. Updated roughly weekly, a few days behind.
- `PortWatch_chokepoints_database`: chokepoint names and coordinates for the map.
- `Daily_Ports_Data`: port calls and estimated import/export volumes (t) per port and day;
  only the ports configured in `config/monitor.yaml` are downloaded (5.9 m rows in total).
- `portwatch_disruptions_database`: disruption events (cyclones, earthquakes, conflicts, ...).

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
PORTS_DAILY_URL = f"{SERVICES}/Daily_Ports_Data/FeatureServer/0/query"
PORTS_URL = f"{SERVICES}/PortWatch_ports_database/FeatureServer/0/query"
EVENTS_URL = f"{SERVICES}/portwatch_disruptions_database/FeatureServer/0/query"
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


def daily_dir(raw_dir: Path, dataset: str = "chokepoints_daily") -> Path:
    return raw_dir / "portwatch" / dataset


def _read_stored(raw_dir: Path, dataset: str, columns: list[str]) -> pd.DataFrame | None:
    files = sorted(daily_dir(raw_dir, dataset).glob("*.parquet"))
    if not files:
        return None
    return pd.concat((pd.read_parquet(f, columns=columns) for f in files), ignore_index=True)


def last_stored_date(raw_dir: Path, dataset: str = "chokepoints_daily") -> date | None:
    """Latest day in all raw files of a daily dataset, or None before the first download."""
    stored = _read_stored(raw_dir, dataset, ["date"])
    if stored is None or stored.empty:
        return None
    return pd.to_datetime(stored["date"]).max().date()


def _write_raw(rows: list[dict], folder: Path) -> Path:
    """One Parquet file per download, named by download time; never overwritten."""
    raw = pd.DataFrame(rows)
    fetched_at = datetime.now(UTC)
    raw["fetched_at"] = fetched_at
    # Microseconds in the name: two downloads in the same second must not share a file.
    path = folder / f"{fetched_at:%Y%m%dT%H%M%S%f}.parquet"
    if path.exists():
        raise FileExistsError(f"raw files are never overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(path, index=False)
    return path


def _since_filter(last: date | None, revision_days: int) -> str:
    if last is None:
        return "1=1"
    since = last - timedelta(days=revision_days)
    return f"date >= DATE '{since.isoformat()}'"


def ingest_chokepoint_transits(
    raw_dir: Path,
    revision_days: int = 14,
    session: requests.Session | None = None,
    sleep: Sleep = time.sleep,
) -> Path | None:
    """Fetch new (and recently revised) days; returns the new raw file or None if nothing new."""
    session = session or requests.Session()
    where = _since_filter(last_stored_date(raw_dir), revision_days)
    rows = query_all(session, DAILY_URL, where, "*", "date,portid", sleep)
    if not rows:
        logger.info("PortWatch: no rows for %s", where)
        return None
    path = _write_raw(rows, daily_dir(raw_dir))
    logger.info("PortWatch chokepoints: %s rows (%s) -> %s", len(rows), where, path)
    return path


def _id_list(ids: list[str]) -> str:
    return ", ".join(f"'{i}'" for i in ids)


def ingest_port_activity(
    raw_dir: Path,
    port_ids: list[str],
    revision_days: int = 14,
    session: requests.Session | None = None,
    sleep: Sleep = time.sleep,
) -> Path | None:
    """Daily port calls and trade volume estimates for selected ports (incremental).

    Ports already stored are updated from (last date - revision_days); ports added to the
    configuration later get their full history.
    """
    session = session or requests.Session()
    dataset = "ports_daily"
    stored = _read_stored(raw_dir, dataset, ["date", "portid"])
    stored_ids = set() if stored is None else set(stored["portid"])
    new_ids = [p for p in port_ids if p not in stored_ids]
    known_ids = [p for p in port_ids if p in stored_ids]

    rows: list[dict] = []
    if new_ids:
        where = f"portid IN ({_id_list(new_ids)})"
        rows += query_all(session, PORTS_DAILY_URL, where, "*", "date,portid", sleep)
    if known_ids:
        since = _since_filter(last_stored_date(raw_dir, dataset), revision_days)
        where = f"portid IN ({_id_list(known_ids)}) AND {since}"
        rows += query_all(session, PORTS_DAILY_URL, where, "*", "date,portid", sleep)
    if not rows:
        return None
    path = _write_raw(rows, daily_dir(raw_dir, dataset))
    logger.info("PortWatch ports: %s rows -> %s", len(rows), path)
    return path


def ingest_ports_reference(
    raw_dir: Path,
    port_ids: list[str],
    session: requests.Session | None = None,
    sleep: Sleep = time.sleep,
) -> Path:
    """Names, countries and coordinates of the selected ports (refetched when ids change)."""
    path = raw_dir / "portwatch" / "ports.parquet"
    if path.exists() and set(port_ids) <= set(pd.read_parquet(path)["portid"]):
        return path
    session = session or requests.Session()
    where = f"portid IN ({_id_list(port_ids)})"
    fields = "portid,portname,country,ISO3,lat,lon"
    rows = query_all(session, PORTS_URL, where, fields, "portid", sleep)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def ingest_events(
    raw_dir: Path, session: requests.Session | None = None, sleep: Sleep = time.sleep
) -> Path:
    """Download the full disruption-event database (about 130 events) as a new raw file."""
    session = session or requests.Session()
    fields = (
        "eventid,eventtype,eventname,alertlevel,country,fromdate,todate,lat,long,"
        "affectedports,n_affectedports,htmldescription"
    )
    rows = query_all(session, EVENTS_URL, "1=1", fields, "eventid", sleep)
    return _write_raw(rows, raw_dir / "portwatch" / "events")


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
