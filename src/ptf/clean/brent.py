"""Parse the raw FRED Brent CSV and aggregate it to annual average prices."""

from pathlib import Path

import pandas as pd


def parse_brent_csv(path: Path) -> pd.DataFrame:
    """Daily prices with columns `date`, `usd_per_bbl`; days without a quote are dropped.

    FRED marks missing days (holidays) with an empty field or ".", depending on the export.
    """
    daily = pd.read_csv(path, na_values=["."])
    daily.columns = ["date", "usd_per_bbl"]
    daily["date"] = pd.to_datetime(daily["date"])
    daily["usd_per_bbl"] = pd.to_numeric(daily["usd_per_bbl"])
    return daily.dropna(subset=["usd_per_bbl"]).reset_index(drop=True)


def annual_brent(daily: pd.DataFrame) -> pd.DataFrame:
    """Annual mean price and number of quoted days per year."""
    return (
        daily.assign(year=daily["date"].dt.year)
        .groupby("year", as_index=False)
        .agg(brent_usd_per_bbl=("usd_per_bbl", "mean"), quoted_days=("usd_per_bbl", "size"))
    )
