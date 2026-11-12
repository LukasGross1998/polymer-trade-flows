"""Key figures of the shipping monitor, computed from the clean daily transit table.

Daily transit counts are noisy (weekdays, convoys, single large days), so everything works on
a rolling mean. "Normal" for a given day is the average daily traffic in the same ISO calendar
week across the baseline years (2019-2023), which removes seasonality: comparing November
with an annual average would flag every quiet season as a disruption.
"""

import pandas as pd

from ptf.clean.portwatch import VESSEL_TYPES
from ptf.monitor.config import MonitorConfig

# 364 days = exactly 52 weeks, so the comparison day falls on the same weekday a year earlier.
ONE_YEAR = pd.Timedelta(days=364)


def daily_series(transits: pd.DataFrame, vessel_type: str) -> pd.DataFrame:
    """Columns date, chokepoint_id, chokepoint, value for one vessel type (e.g. 'container')."""
    column = VESSEL_TYPES[vessel_type]
    series = transits[["date", "chokepoint_id", "chokepoint", column]]
    return series.rename(columns={column: "value"}).sort_values(["chokepoint_id", "date"])


def add_rolling_mean(series: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Add `rolling`: mean of the last `window_days` days per chokepoint (NaN until full)."""
    rolling = series.groupby("chokepoint_id")["value"].transform(
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
    """Normal traffic per chokepoint and calendar week, from the baseline years.

    `baseline` is the mean over the years of each year's average daily traffic in that week;
    `baseline_low` / `baseline_high` are the lowest and highest of those yearly averages
    (the band shown in the chart).
    """
    with_week = pd.concat([series, _iso_year_week(series["date"])], axis=1)
    base = with_week[with_week["iso_year"].isin(baseline_years)]
    per_year = base.groupby(["chokepoint_id", "iso_year", "week"], as_index=False)["value"].mean()
    return (
        per_year.groupby(["chokepoint_id", "week"])["value"]
        .agg(baseline="mean", baseline_low="min", baseline_high="max")
        .reset_index()
    )


def compare_to_baseline(
    series: pd.DataFrame, baseline: pd.DataFrame, threshold: float
) -> pd.DataFrame:
    """Add baseline columns, `deviation_pct` and `is_disrupted` to a series with `rolling`."""
    with_week = pd.concat([series, _iso_year_week(series["date"])[["week"]]], axis=1)
    table = with_week.merge(baseline, on=["chokepoint_id", "week"], how="left")
    table["deviation_pct"] = (table["rolling"] / table["baseline"] - 1) * 100
    table["is_disrupted"] = (table["rolling"] < threshold * table["baseline"]).fillna(False)
    return table


def monitor_table(transits: pd.DataFrame, vessel_type: str, config: MonitorConfig) -> pd.DataFrame:
    """Daily series with rolling mean, baseline and deviation for every chokepoint."""
    series = add_rolling_mean(daily_series(transits, vessel_type), config.rolling_window_days)
    baseline = weekly_baseline(series, config.baseline_years)
    return compare_to_baseline(series, baseline, config.disruption_threshold)


def latest_status(table: pd.DataFrame) -> pd.DataFrame:
    """One row per chokepoint at the latest date, plus `yoy_pct` against 52 weeks earlier."""
    latest_date = table["date"].max()
    latest = table[table["date"] == latest_date].copy()
    year_ago = table[table["date"] == latest_date - ONE_YEAR].set_index("chokepoint_id")
    previous = latest["chokepoint_id"].map(year_ago["rolling"])
    latest["yoy_pct"] = (latest["rolling"] / previous - 1) * 100
    return latest.reset_index(drop=True)


def diversion_ratio(transits: pd.DataFrame, config: MonitorConfig) -> pd.DataFrame:
    """Share of container ships taking the Cape route instead of the Red Sea (rolling).

    cape_share = Cape / (Cape + Bab el-Mandeb). Before the crisis roughly a quarter, after
    the attacks from late 2023 on most container traffic between Asia and Europe goes
    around Africa.
    """
    series = add_rolling_mean(daily_series(transits, "container"), config.rolling_window_days)
    wide = series.pivot(index="date", columns="chokepoint_id", values="rolling")
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
