"""Download the New York Fed Global Supply Chain Pressure Index (GSCPI) spreadsheet.

Raw layer: one file per download in `data/raw/gscpi/`, never overwritten.
"""

from datetime import UTC, datetime
from pathlib import Path

import requests

from ptf.ingest.fred import is_fresh


def gscpi_dir(raw_dir: Path) -> Path:
    return raw_dir / "gscpi"


def latest_gscpi(raw_dir: Path) -> Path | None:
    files = sorted(gscpi_dir(raw_dir).glob("*.xls"))
    return files[-1] if files else None


def ingest_gscpi(
    raw_dir: Path, url: str, max_age_days: float = 1, session: requests.Session | None = None
) -> Path | None:
    """Download the spreadsheet unless the newest copy is younger than `max_age_days`."""
    now = datetime.now(UTC)
    if is_fresh(latest_gscpi(raw_dir), max_age_days, now):
        return None
    session = session or requests.Session()
    response = session.get(url, timeout=60)
    response.raise_for_status()
    # Saved as .xls: the server's ".xlsx" file is really in the old Excel format.
    path = gscpi_dir(raw_dir) / f"{now:%Y%m%dT%H%M%S%f}.xls"
    if path.exists():
        raise FileExistsError(f"raw files are never overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path
