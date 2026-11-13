"""Key figures of the shipping monitor, for chokepoints and ports alike.

All functions work on a "location series" with columns date, location_id, location, value:
a chokepoint and a vessel type, or a port and a metric (port calls, import volume, ...).

Daily counts are noisy (weekdays, convoys, single large days), so everything works on a
rolling mean. "Normal" for a given day is the average daily value in the same ISO calendar
week across the baseline years (2019-2023), which removes seasonality: comparing November
with an annual average would flag every quiet season as a disruption.
"""

import pandas as pd

from ptf.shipping.config import MonitorConfig
from ptf.shipping.vocabulary import VESSEL_TYPES

# 364 days = exactly 52 weeks, so the comparison day falls on the same weekday a year earlier.
ONE_YEAR = pd.Timedelta(days=364)


def location_series(
    frame: pd.DataFrame, id_column: str, name_column: str, value_column: str
) -> pd.DataFrame:
    """Columns date, location_id, location, value, sorted by location and date."""
    series = frame[["date", id_column, name_column, value_column]].rename(
        columns={id_column: "location_id", name_column: "location", value_column: "value"}
    )
    return series.sort_values(["location_id", "date"]).reset_index(drop=True)


def daily_series(transits: pd.DataFrame, vessel_type: str) -> pd.DataFrame:
    """Chokepoint transits of one vessel type (e.g. 'container') as a location series."""
    return location_series(transits, "chokepoint_id", "chokepoint", VESSEL_TYPES[vessel_type])


def port_series(ports: pd.DataFrame, metric: str) -> pd.DataFrame:
    """One port metric (e.g. 'portcalls', 'export') as a location series."""
    return location_series(ports, "port_id", "port", metric)


def add_rolling_mean(series: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Add `rolling`: mean of the last `window_days` days per location (NaN until full)."""
    rolling = series.groupby("location_id")["value"].transform(
        lambda values: values.rolling(window_days, min_periods=window_days).mean()
    )
    return series.assign(rolling=rolling)


def _iso_year_week(dates: pd.Series) -> pd.DataFrame:
    """ISO year and week; week 53 (only in some years) is folded into week 52."""
    iso = dates.dt.isocalendar()
    return pd.DataFrame(
        {"iso_year": iso["year"].astype(int), "week": iso["week"].clip(upper=52).astype(int)},
        index=dates.index,
    )


def weekly_baseline(series: pd.DataFrame, baseline_years: list[int]) -> pd.DataFrame:
    """Normal level per location and calendar week, from the baseline years.

    `baseline` is the mean over the years of each year's average daily value in that week;
    `baseline_low` / `baseline_high` are the lowest and highest of those yearly averages
    (the band shown in the chart).
    """
    with_week = pd.concat([series, _iso_year_week(series["date"])], axis=1)
    base = with_week[with_week["iso_year"].isin(baseline_years)]
    per_year = base.groupby(["location_id", "iso_year", "week"], as_index=False)["value"].mean()
    return (
        per_year.groupby(["location_id", "week"])["value"]
        .agg(baseline="mean", baseline_low="min", baseline_high="max")
        .reset_index()
    )


def compare_to_baseline(
    series: pd.DataFrame, baseline: pd.DataFrame, threshold: float, min_baseline: float = 0.0
) -> pd.DataFrame:
    """Add baseline columns, `deviation_pct` and `is_disrupted` to a series with `rolling`.

    Locations whose normal level is below `min_baseline` per day are never flagged: with so
    few ships, percentage changes are noise.
    """
    with_week = pd.concat([series, _iso_year_week(series["date"])[["week"]]], axis=1)
    table = with_week.merge(baseline, on=["location_id", "week"], how="left")
    table["deviation_pct"] = (table["rolling"] / table["baseline"] - 1) * 100
    below_threshold = table["rolling"] < threshold * table["baseline"]
    enough_traffic = table["baseline"] >= min_baseline
    table["is_disrupted"] = (below_threshold & enough_traffic).fillna(False)
    return table


def series_table(series: pd.DataFrame, config: MonitorConfig) -> pd.DataFrame:
    """Rolling mean, baseline and deviation for every location of a location series."""
    series = add_rolling_mean(series, config.rolling_window_days)
    baseline = weekly_baseline(series, config.baseline_years)
    return compare_to_baseline(
        series, baseline, config.disruption_threshold, config.min_baseline_per_day
    )


def monitor_table(transits: pd.DataFrame, vessel_type: str, config: MonitorConfig) -> pd.DataFrame:
    """Chokepoints: daily series with rolling mean, baseline and deviation."""
    return series_table(daily_series(transits, vessel_type), config)


def port_table(ports: pd.DataFrame, metric: str, config: MonitorConfig) -> pd.DataFrame:
    """Ports: daily series with rolling mean, baseline and deviation."""
    return series_table(port_series(ports, metric), config)


def latest_status(table: pd.DataFrame) -> pd.DataFrame:
    """One row per location at the latest date, plus `yoy_pct` against 52 weeks earlier."""
    latest_date = table["date"].max()
    latest = table[table["date"] == latest_date].copy()
    year_ago = table[table["date"] == latest_date - ONE_YEAR].set_index("location_id")
    previous = latest["location_id"].map(year_ago["rolling"])
    latest["yoy_pct"] = (latest["rolling"] / previous - 1) * 100
    return latest.reset_index(drop=True)


def diversion_ratio(transits: pd.DataFrame, config: MonitorConfig) -> pd.DataFrame:
    """Share of container ships taking the Cape route instead of the Red Sea (rolling).

    cape_share = Cape / (Cape + Bab el-Mandeb). Before the crisis roughly a quarter, after
    the attacks from late 2023 on most container traffic between Asia and Europe goes
    around Africa.
    """
    series = add_rolling_mean(daily_series(transits, "container"), config.rolling_window_days)
    wide = series.pivot(index="date", columns="location_id", values="rolling")
    red_sea = wide[config.red_sea.red_sea_route]
    cape = wide[config.red_sea.cape_route]
    return pd.DataFrame(
        {
            "date": wide.index,
            "red_sea_rolling": red_sea.to_numpy(),
            "cape_rolling": cape.to_numpy(),
            "cape_share": (cape / (cape + red_sea)).to_numpy(),
        }
    ).reset_index(drop=True)


# Vessel classes without "total", in display order (spec 008).
VESSEL_CLASSES = ["container", "tanker", "dry_bulk", "general_cargo", "roro"]


def vessel_mix(
    transits: pd.DataFrame, chokepoint_id: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Average daily transits per vessel class at one chokepoint between `start` and `end`.

    Columns: vessel_type, transits (mean per day), share (of all classes, 0-1).
    """
    rows = transits[
        (transits["chokepoint_id"] == chokepoint_id)
        & (transits["date"] >= start)
        & (transits["date"] <= end)
    ]
    means = [rows[VESSEL_TYPES[v]].mean() if len(rows) else 0.0 for v in VESSEL_CLASSES]
    mix = pd.DataFrame({"vessel_type": VESSEL_CLASSES, "transits": means}).fillna(0.0)
    total = mix["transits"].sum()
    return mix.assign(share=mix["transits"] / total if total else 0.0)


def capacity_mix(
    transits: pd.DataFrame, chokepoint_id: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Share of carrying capacity by class where PortWatch gives it: container, tanker, other.

    "Other" (dry bulk, general cargo, RoRo) = total capacity - container - tanker.
    """
    rows = transits[
        (transits["chokepoint_id"] == chokepoint_id)
        & (transits["date"] >= start)
        & (transits["date"] <= end)
    ]
    total = rows["capacity"].sum()
    container = rows["capacity_container"].sum()
    tanker = rows["capacity_tanker"].sum()
    parts = {"container": container, "tanker": tanker, "other": total - container - tanker}
    mix = pd.DataFrame({"vessel_type": list(parts), "capacity_t": list(parts.values())})
    return mix.assign(share=mix["capacity_t"] / total if total else 0.0)


def class_status(transits: pd.DataFrame, chokepoint_id: str, config: MonitorConfig) -> pd.DataFrame:
    """Latest rolling mean against the seasonal normal for each vessel class at one chokepoint.

    The same method as for all vessels (rolling mean vs. same calendar week in the baseline
    years), applied per class. Columns: vessel_type, rolling, baseline, deviation_pct,
    is_disrupted.
    """
    rows = []
    one = transits[transits["chokepoint_id"] == chokepoint_id]
    for vessel_type in VESSEL_CLASSES:
        status = latest_status(monitor_table(one, vessel_type, config))
        if status.empty:
            continue
        latest = status.iloc[0]
        rows.append(
            {
                "vessel_type": vessel_type,
                "rolling": latest["rolling"],
                "baseline": latest["baseline"],
                "deviation_pct": latest["deviation_pct"],
                "is_disrupted": bool(latest["is_disrupted"]),
            }
        )
    return pd.DataFrame(
        rows, columns=["vessel_type", "rolling", "baseline", "deviation_pct", "is_disrupted"]
    )
