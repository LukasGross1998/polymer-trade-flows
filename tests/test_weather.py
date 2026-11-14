"""Marine weather (spec 009): download with a fake session and storm warnings."""

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from helpers import FakeResponse, FakeSession

from ptf.shipping import weather
from ptf.shipping.config import WeatherConfig

CONFIG = WeatherConfig()  # waves 4 / 6 m, gusts 63.0 / 88.9 km/h (34 / 48 knots)


def daily(days: list[str], **values: list[Any]) -> dict[str, Any]:
    return {"daily": {"time": days, **values}}


def write_locations(raw_dir: Path) -> None:
    (raw_dir / "portwatch").mkdir(parents=True)
    pd.DataFrame(
        {"portid": ["chokepoint6"], "portname": ["Strait of Hormuz"], "lat": [26.6], "lon": [56.3]}
    ).to_parquet(raw_dir / "portwatch" / "chokepoints.parquet")
    pd.DataFrame(
        {
            "portid": ["port24", "port999"],
            "portname": ["Jubail", "Other"],
            "lat": [27.0, 0],
            "lon": [49.7, 0],
        }
    ).to_parquet(raw_dir / "portwatch" / "ports.parquet")


def test_download_for_all_locations_in_two_requests(tmp_path: Path) -> None:
    write_locations(tmp_path)
    days = ["2026-11-13", "2026-11-14"]
    marine = FakeResponse(200)
    marine._payload = [  # type: ignore[assignment]  # Open-Meteo returns a list here
        daily(days, wave_height_max=[1.0, 4.5]),
        daily(days, wave_height_max=[None, None]),  # on land: no waves
    ]
    wind = FakeResponse(200)
    wind._payload = [  # type: ignore[assignment]
        daily(days, wind_gusts_10m_max=[40.0, 95.0], wind_speed_10m_max=[20.0, 60.0]),
        daily(days, wind_gusts_10m_max=[30.0, 35.0], wind_speed_10m_max=[10.0, 12.0]),
    ]
    session = FakeSession([marine, wind])

    path = weather.ingest_weather(tmp_path, ["port24"], CONFIG, session=session)  # type: ignore[arg-type]

    assert path is not None
    table = pd.read_parquet(path).set_index(["location_id", "date"])
    assert session.calls[0]["params"]["latitude"] == "26.6000,27.0000"  # port999 not configured
    assert table.loc[("chokepoint6", pd.Timestamp("2026-11-14")), "wind_gusts_kmh"] == 95.0
    assert pd.isna(table.loc[("port24", pd.Timestamp("2026-11-13")), "wave_height_m"])
    assert set(table["location_type"]) == {"chokepoint", "port"}


def test_storm_level_on_both_sides_of_the_thresholds() -> None:
    assert weather.storm_level(3.9, 62.9, CONFIG) == weather.GREEN
    assert weather.storm_level(4.0, None, CONFIG) == weather.AMBER
    assert weather.storm_level(None, 63.0, CONFIG) == weather.AMBER
    assert weather.storm_level(5.9, 88.8, CONFIG) == weather.AMBER
    assert weather.storm_level(1.0, 88.9, CONFIG) == weather.RED
    assert weather.storm_level(6.0, 10.0, CONFIG) == weather.RED


def test_storm_warnings_only_from_today_worst_first() -> None:
    table = pd.DataFrame(
        {
            "location_id": ["a", "a", "b", "b"],
            "date": pd.to_datetime(["2026-11-12", "2026-11-15", "2026-11-14", "2026-11-16"]),
            "wave_height_m": [9.0, 4.2, 1.0, 1.0],
            "wind_gusts_kmh": [10.0, 10.0, 95.0, 20.0],
        }
    )

    warnings = weather.storm_warnings(table, pd.Timestamp("2026-11-13"), CONFIG)

    assert warnings[["location_id", "level"]].values.tolist() == [["b", "red"], ["a", "amber"]]


def test_no_locations_no_download(tmp_path: Path) -> None:
    assert weather.ingest_weather(tmp_path, [], CONFIG, session=FakeSession([])) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("payload_is_dict", [True])
def test_single_location_answer_is_a_dict(tmp_path: Path, payload_is_dict: bool) -> None:
    (tmp_path / "portwatch").mkdir(parents=True)
    pd.DataFrame({"portid": ["chokepoint6"], "lat": [26.6], "lon": [56.3]}).to_parquet(
        tmp_path / "portwatch" / "chokepoints.parquet"
    )
    marine = FakeResponse(200, daily(["2026-11-13"], wave_height_max=[2.0]))
    wind = FakeResponse(
        200, daily(["2026-11-13"], wind_gusts_10m_max=[50.0], wind_speed_10m_max=[30.0])
    )

    path = weather.ingest_weather(tmp_path, [], CONFIG, session=FakeSession([marine, wind]))  # type: ignore[arg-type]

    assert path is not None and pd.read_parquet(path)["wave_height_m"].tolist() == [2.0]
