"""Annual average Brent prices for the model, from the daily FRED series."""

import pandas as pd


def annual_brent(daily: pd.DataFrame) -> pd.DataFrame:
    """Annual mean price and number of quoted days per year."""
    return (
        daily.assign(year=daily["date"].dt.year)
        .groupby("year", as_index=False)
        .agg(brent_usd_per_bbl=("usd_per_bbl", "mean"), quoted_days=("usd_per_bbl", "size"))
    )
