"""Indicators from the long `market_series` table (FRED series, GSCPI).

Pure functions: DataFrame in, number or DataFrame out. The app only displays the results.
"""

import pandas as pd


def series(market: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """Columns date, value of one series, sorted by date."""
    one = market[market["series_id"] == series_id][["date", "value"]]
    return one.sort_values("date").reset_index(drop=True)


def latest(market: pd.DataFrame, series_id: str) -> tuple[pd.Timestamp, float] | None:
    """Date and value of the newest observation, or None if the series is missing."""
    one = series(market, series_id)
    if one.empty:
        return None
    last = one.iloc[-1]
    return last["date"], float(last["value"])


def change_pct(market: pd.DataFrame, series_id: str, days: int) -> float | None:
    """Change of the newest value against the last value at least `days` days earlier, in %."""
    one = series(market, series_id)
    if one.empty:
        return None
    newest = one.iloc[-1]
    earlier = one[one["date"] <= newest["date"] - pd.Timedelta(days=days)]
    if earlier.empty:
        return None
    return float((newest["value"] / earlier.iloc[-1]["value"] - 1) * 100)


def monthly_mean(market: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """Monthly average (date = first day of the month), to compare daily with monthly series."""
    one = series(market, series_id)
    monthly = one.set_index("date")["value"].resample("MS").mean().dropna()
    return monthly.reset_index()


def gas_spread(market: pd.DataFrame, region_id: str, us_id: str = "DHHNGSP") -> pd.DataFrame:
    """Monthly gas price of a region minus US Henry Hub (USD/MMBtu).

    A wide spread means cheap US feedstock: the cost advantage of ethane-based US
    polyethylene against naphtha- and gas-based producers in Europe and Asia.
    """
    region = monthly_mean(market, region_id).set_index("date")["value"]
    us = monthly_mean(market, us_id).set_index("date")["value"]
    spread = (region - us).dropna()
    return spread.rename("value").reset_index()


def indexed(market: pd.DataFrame, series_ids: list[str], start: pd.Timestamp) -> pd.DataFrame:
    """Series rebased to 100 at their first observation on or after `start`.

    Lets series with different units share one axis (instead of a misleading dual axis).
    Columns: date, series_id, value.
    """
    frames = []
    for series_id in series_ids:
        one = series(market, series_id)
        one = one[one["date"] >= start]
        if one.empty:
            continue
        frames.append(
            one.assign(value=one["value"] / one["value"].iloc[0] * 100, series_id=series_id)
        )
    if not frames:
        return pd.DataFrame(columns=["date", "series_id", "value"])
    return pd.concat(frames, ignore_index=True)[["date", "series_id", "value"]]
