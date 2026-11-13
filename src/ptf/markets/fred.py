"""Download economic time series from FRED (St. Louis Fed) as CSV, without an API key.

Raw layer: one CSV per download, byte for byte as served, in `data/raw/fred/{series_id}/`.
Files are never overwritten; the clean layer reads the newest one.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def series_dir(raw_dir: Path, series_id: str) -> Path:
    return raw_dir / "fred" / series_id


def latest_raw(raw_dir: Path, series_id: str) -> Path | None:
    """Newest downloaded CSV of a series (file names sort by download time)."""
    files = sorted(series_dir(raw_dir, series_id).glob("*.csv"))
    return files[-1] if files else None


def is_fresh(path: Path | None, max_age_days: float, now: datetime) -> bool:
    if path is None:
        return False
    downloaded = datetime.strptime(path.stem, "%Y%m%dT%H%M%S%f").replace(tzinfo=UTC)
    return now - downloaded < timedelta(days=max_age_days)


def download_series(raw_dir: Path, series_id: str, session: requests.Session) -> Path:
    response = session.get(FRED_CSV_URL, params={"id": series_id}, timeout=60)
    response.raise_for_status()
    path = series_dir(raw_dir, series_id) / f"{datetime.now(UTC):%Y%m%dT%H%M%S%f}.csv"
    if path.exists():
        raise FileExistsError(f"raw files are never overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def ingest_fred(
    raw_dir: Path,
    series_ids: list[str],
    max_age_days: float = 1,
    session: requests.Session | None = None,
) -> list[Path]:
    """Download every series whose newest raw file is missing or older than `max_age_days`."""
    session = session or requests.Session()
    now = datetime.now(UTC)
    written = []
    for series_id in series_ids:
        if is_fresh(latest_raw(raw_dir, series_id), max_age_days, now):
            continue
        written.append(download_series(raw_dir, series_id, session))
        logger.info("FRED %s downloaded", series_id)
    return written
