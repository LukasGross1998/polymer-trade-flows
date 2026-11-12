"""Clean market data (FRED series, GSCPI) into one long table `market_series`.

Long format (one row per series and date) keeps all series in one file regardless of their
frequency; the app picks the series it needs.
"""

from pathlib import Path

import pandas as pd

from ptf.ingest.fred import latest_raw
from ptf.ingest.gscpi import latest_gscpi
from ptf.market_config import SeriesConfig

MARKET_COLUMNS = ["date", "series_id", "name", "unit", "frequency", "group", "value"]


def parse_fred_csv(path: Path) -> pd.DataFrame:
    """Columns `date`, `value`; days without a quote are dropped.

    FRED marks missing days (holidays) with an empty field or ".", depending on the export.
    """
    raw = pd.read_csv(path, na_values=["."])
    raw.columns = ["date", "value"]
    raw["date"] = pd.to_datetime(raw["date"])
    raw["value"] = pd.to_numeric(raw["value"])
    return raw.dropna(subset=["value"]).reset_index(drop=True)


def parse_gscpi(path: Path) -> pd.DataFrame:
    """Columns `date`, `value` from the NY Fed spreadsheet."""
    return tidy_gscpi(pd.read_excel(path, engine="calamine", header=None))


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


def clean_market_series(raw_dir: Path, series: list[SeriesConfig]) -> pd.DataFrame:
    """All configured FRED series plus the GSCPI, from their newest raw files."""
    frames = []
    for item in series:
        path = latest_raw(raw_dir, item.id)
        if path is None:
            continue
        frames.append(
            parse_fred_csv(path).assign(**item.model_dump(exclude={"id"}), series_id=item.id)
        )

    gscpi_path = latest_gscpi(raw_dir)
    if gscpi_path is not None:
        frames.append(
            parse_gscpi(gscpi_path).assign(
                series_id="GSCPI",
                name="Global Supply Chain Pressure Index (NY Fed)",
                unit="std. dev. from average",
                frequency="monthly",
                group="supply_chain",
            )
        )
    if not frames:
        raise FileNotFoundError(f"no market data in {raw_dir}")
    return pd.concat(frames, ignore_index=True)[MARKET_COLUMNS]
