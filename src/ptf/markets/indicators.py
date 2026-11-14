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


def is_usd_based(market: pd.DataFrame, series_id: str) -> bool:
    """Prices in USD (unit "USD/...") and the US producer price indices (USD-based).

    Exchange rates are excluded: "USD/EUR" is a rate, not a price to convert.
    """
    meta = market.loc[market["series_id"] == series_id, ["unit", "group"]]
    if meta.empty:
        return False
    unit, group = meta.iloc[0]["unit"], meta.iloc[0]["group"]
    if group == "fx":
        return False
    return str(unit).startswith("USD/") or group == "freight_polymers"


def usd_to_eur(
    values: pd.DataFrame, usd_per_eur: pd.DataFrame, monthly: bool = False
) -> pd.DataFrame:
    """Convert a date/value series from USD to EUR (value / USD per EUR).

    Daily values use the rate of the same day, or the most recent earlier one (FRED has no
    rate on holidays). Monthly values use the average rate of that month, because a monthly
    price is an average over the month too.
    """
    rates = usd_per_eur.sort_values("date")[["date", "value"]].rename(columns={"value": "rate"})
    if monthly:
        rates = rates.set_index("date")["rate"].resample("MS").mean().dropna().reset_index()
        merged = values.merge(rates, on="date", how="left")
    else:
        merged = pd.merge_asof(values.sort_values("date"), rates, on="date", direction="backward")
    merged = merged.dropna(subset=["rate"])
    return merged.assign(value=merged["value"] / merged["rate"])[["date", "value"]]


def in_currency(market: pd.DataFrame, currency: str, fx_id: str = "DEXUSEU") -> pd.DataFrame:
    """The long market table with all USD-based series converted to `currency` (USD or EUR).

    Other series (exchange rates, GSCPI) are returned unchanged. Units say the new currency.
    """
    if currency == "USD":
        return market
    if currency != "EUR":
        raise ValueError(f"unsupported currency {currency!r}")
    rates = series(market, fx_id)
    frames = []
    for series_id, one in market.groupby("series_id", sort=False):
        if is_usd_based(market, str(series_id)) and not rates.empty:
            monthly = one["frequency"].iloc[0] == "monthly"
            converted = usd_to_eur(one[["date", "value"]], rates, monthly=monthly)
            meta = one.drop(columns=["date", "value"]).iloc[0]
            one = converted.assign(**{str(k): v for k, v in meta.items()})
            one["unit"] = str(meta["unit"]).replace("USD", "EUR")
        frames.append(one)
    return pd.concat(frames, ignore_index=True)[market.columns]


def monthly_table(market: pd.DataFrame, series_ids: list[str]) -> pd.DataFrame:
    """Monthly averages of several series as a long table (date, series_id, value).

    Daily and monthly series become comparable: one point per month for each.
    """
    frames = [
        monthly_mean(market, series_id).assign(series_id=series_id)
        for series_id in series_ids
        if not series(market, series_id).empty
    ]
    if not frames:
        return pd.DataFrame(columns=["date", "series_id", "value"])
    return pd.concat(frames, ignore_index=True)[["date", "series_id", "value"]]


def cny_to_usd(values: pd.DataFrame, cny_per_usd: pd.DataFrame) -> pd.DataFrame:
    """Convert a date/value series from CNY to USD with the same-day (or last earlier) rate.

    FRED's DEXCHUS is Chinese yuan per US dollar, so USD = CNY / rate.
    """
    rates = cny_per_usd.sort_values("date")[["date", "value"]].rename(columns={"value": "rate"})
    merged = pd.merge_asof(values.sort_values("date"), rates, on="date", direction="backward")
    merged = merged.dropna(subset=["rate"])
    return merged.assign(value=merged["value"] / merged["rate"])[["date", "value"]]
