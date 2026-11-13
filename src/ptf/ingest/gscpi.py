"""Download the New York Fed Global Supply Chain Pressure Index (GSCPI) spreadsheet.

Raw layer: one file per download in `data/raw/gscpi/`, never overwritten.
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
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


def tidy_gscpi(sheet: pd.DataFrame) -> pd.DataFrame:
    """The sheet has a header row ("Date", "GSCPI"), then a few empty rows, then the data."""
    raw = sheet.iloc[1:, :2].dropna()
    raw.columns = ["date", "value"]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(raw["date"], format="%d-%b-%Y"),
            "value": pd.to_numeric(raw["value"]),
        }
    ).reset_index(drop=True)


def write_gscpi_landing(raw_dir: Path) -> Path:
    """Parse the newest spreadsheet into `gscpi/landing_gscpi.parquet` for dbt.

    DuckDB cannot read the old .xls format, so this one source needs Python. Without any
    download an empty landing file is written, so the dbt models still build.
    """
    path = gscpi_dir(raw_dir) / "landing_gscpi.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    source = latest_gscpi(raw_dir)
    if source is None:
        landing = pd.DataFrame(
            {"date": pd.Series(dtype="datetime64[ns]"), "value": pd.Series(dtype=float)}
        )
    else:
        landing = tidy_gscpi(pd.read_excel(source, engine="calamine", header=None))
    landing.to_parquet(path, index=False)
    return path
