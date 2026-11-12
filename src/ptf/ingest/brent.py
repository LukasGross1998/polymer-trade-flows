"""Brent crude oil spot price from FRED (St. Louis Fed), downloaded as CSV without an API key.

Raw layer: the CSV exactly as served. The clean layer parses it and aggregates to annual
averages (see `ptf.clean.brent`).
"""

from pathlib import Path

import requests

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def raw_brent_path(raw_dir: Path, series: str) -> Path:
    return raw_dir / "brent" / f"{series}.csv"


def ingest_brent(
    raw_dir: Path,
    series: str = "DCOILBRENTEU",
    session: requests.Session | None = None,
    force: bool = False,
) -> Path:
    """Download the full daily series once; pass `force=True` to refresh it."""
    path = raw_brent_path(raw_dir, series)
    if path.exists() and not force:
        return path
    session = session or requests.Session()
    response = session.get(FRED_CSV_URL, params={"id": series}, timeout=60)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path
