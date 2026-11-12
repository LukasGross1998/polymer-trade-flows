"""Monitor metrics on small made-up series that can be checked by hand."""

import pandas as pd
import pytest
from conftest import REPO_ROOT

from ptf.monitor.config import MonitorConfig, load_monitor_config
from ptf.monitor.metrics import (
    add_rolling_mean,
    compare_to_baseline,
    diversion_ratio,
    latest_status,
    monitor_table,
    weekly_baseline,
)

CONFIG = MonitorConfig.model_validate(
    {
        "baseline_years": [2019],
        "rolling_window_days": 3,
        "disruption_threshold": 0.7,
        "min_baseline_per_day": 2.0,
        "red_sea": {"red_sea_route": "red", "cape_route": "cape"},
        "revision_days": 14,
    }
)


def transits(
    chokepoint_id: str, start: str, values: list[int], column: str = "n_container"
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="D")
    frame = pd.DataFrame(
        {"date": dates, "chokepoint_id": chokepoint_id, "chokepoint": chokepoint_id}
    )
    for vessel_column in [
        "n_total",
        "n_container",
        "n_tanker",
        "n_dry_bulk",
        "n_general_cargo",
        "n_roro",
    ]:
        frame[vessel_column] = 0
    frame[column] = values
    return frame


def test_project_monitor_config_is_valid() -> None:
    config = load_monitor_config(REPO_ROOT / "config" / "monitor.yaml")

    assert config.baseline_years == [2019, 2020, 2021, 2022, 2023]
    assert config.red_sea.red_sea_route == "chokepoint4"


def test_rolling_mean_needs_a_full_window() -> None:
    series = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=4),
            "chokepoint_id": "x",
            "value": [1, 2, 3, 4],
        }
    )

    rolling = add_rolling_mean(series, window_days=3)["rolling"]

    assert rolling.iloc[:2].isna().all()  # first two days: window not full yet
    assert rolling.iloc[2:].tolist() == [2.0, 3.0]  # (1+2+3)/3, (2+3+4)/3


def test_baseline_averages_each_years_week_then_across_years() -> None:
    # ISO week 2: 2019-01-07..13 (value 10 every day), 2020-01-06..12 (value 20).
    series = pd.concat(
        [
            pd.DataFrame({"date": pd.date_range("2019-01-07", periods=7), "value": 10}),
            pd.DataFrame({"date": pd.date_range("2020-01-06", periods=7), "value": 20}),
        ]
    ).assign(chokepoint_id="x")

    baseline = weekly_baseline(series, [2019, 2020]).set_index("week").loc[2]

    assert baseline["baseline"] == 15
    assert (baseline["baseline_low"], baseline["baseline_high"]) == (10, 20)


def test_traffic_below_threshold_is_flagged_as_disruption() -> None:
    series = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-08", "2024-01-09"]),  # ISO week 2
            "chokepoint_id": "x",
            "rolling": [8.0, 6.0],
        }
    )
    baseline = pd.DataFrame(
        {
            "chokepoint_id": ["x"],
            "week": [2],
            "baseline": [10.0],
            "baseline_low": [9.0],
            "baseline_high": [11.0],
        }
    )

    table = compare_to_baseline(series, baseline, threshold=0.7)

    assert table["deviation_pct"].tolist() == pytest.approx([-20.0, -40.0])
    assert table["is_disrupted"].tolist() == [False, True]  # 8 >= 7, 6 < 7


def test_monitor_table_end_to_end() -> None:
    # Normal 2019: 10 ships a day. Latest week 2024: 4 a day -> -60 %, disrupted.
    data = pd.concat(
        [transits("x", "2019-01-01", [10] * 365), transits("x", "2024-01-01", [4] * 14)]
    )

    status = latest_status(monitor_table(data, "container", CONFIG)).iloc[0]

    assert status["rolling"] == 4
    assert status["deviation_pct"] == pytest.approx(-60)
    assert status["is_disrupted"]


def test_latest_status_compares_with_same_weekday_a_year_earlier() -> None:
    table = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-11-09", "2024-11-07"]),  # 364 days apart, both Thursday
            "chokepoint_id": "x",
            "rolling": [20.0, 5.0],
        }
    )

    status = latest_status(table).iloc[0]

    assert status["yoy_pct"] == pytest.approx(-75)


def test_diversion_ratio_is_cape_share_of_both_routes() -> None:
    data = pd.concat(
        [transits("red", "2024-03-01", [10, 10, 10]), transits("cape", "2024-03-01", [30, 30, 30])]
    )

    ratio = diversion_ratio(data, CONFIG)

    assert ratio["cape_share"].iloc[-1] == pytest.approx(0.75)  # 30 / (30 + 10)


def test_low_traffic_chokepoints_are_not_flagged() -> None:
    series = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-08"]), "chokepoint_id": "x", "rolling": [0.0]}
    )
    baseline = pd.DataFrame(
        {
            "chokepoint_id": ["x"],
            "week": [2],
            "baseline": [0.5],  # half a ship per day is normal here
            "baseline_low": [0.0],
            "baseline_high": [1.0],
        }
    )

    table = compare_to_baseline(series, baseline, threshold=0.7, min_baseline=2.0)

    assert table["deviation_pct"].iloc[0] == pytest.approx(-100)  # still shown
    assert not table["is_disrupted"].iloc[0]  # but not flagged
