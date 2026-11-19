"""Rhine water level at Kaub (spec 019): PEGELONLINE answers, raw files, the mart."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from helpers import PipelineSetup

from ptf.core.warehouse import read_table
from ptf.shipping import rhine

NOW = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
LEVELS = [
    {"timestamp": "2026-11-17T12:00:00+01:00", "value": 61.0},
    {"timestamp": "2026-11-17T12:15:00+01:00", "value": 60.0},
]
STATION = {
    "characteristicValues": [
        {"shortname": "GlW", "longname": "Gleichwertiger WSt ", "value": 77.0}
    ],
    "currentMeasurement": {"timestamp": "x", "value": 113.0, "stateMnwMhw": "normal"},
}


class FakeSession:
    def get(self, url: str, params: dict[str, str], timeout: int) -> object:
        body = LEVELS if url.endswith("measurements.json") else STATION
        return type("R", (), {"json": lambda self: body, "raise_for_status": lambda self: None})()


def test_frames_from_the_api_answers() -> None:
    levels = rhine.levels_frame("KAUB", LEVELS, NOW)
    assert levels["level_cm"].tolist() == [61.0, 60.0]
    assert str(levels["timestamp"].dt.tz) == "UTC"
    station = rhine.station_frame("KAUB", STATION, NOW).set_index("shortname")
    assert station.loc["GlW", "value"] == "77.0" and station.loc["GlW", "longname"] == (
        "Gleichwertiger WSt"
    )
    assert station.loc["stateMnwMhw", "kind"] == "status"


def test_ingest_stores_every_download(tmp_path: Path) -> None:
    levels, station = rhine.ingest_rhine(tmp_path, "KAUB", 31, FakeSession(), NOW)  # type: ignore[arg-type]
    assert pd.read_parquet(levels)["station"].tolist() == ["KAUB", "KAUB"]
    assert pd.read_parquet(station).shape[0] == 2
    with pytest.raises(FileExistsError):
        rhine.ingest_rhine(tmp_path, "KAUB", 31, FakeSession(), NOW)  # type: ignore[arg-type]


def test_empty_raw_files_before_the_first_download(tmp_path: Path) -> None:
    rhine.ensure_raw_files(tmp_path)
    assert pd.read_parquet(next((tmp_path / "rhine" / "levels").glob("*.parquet"))).empty


def test_mart_flags_days_below_the_gauges_glw(warehouse_setup: PipelineSetup) -> None:
    mart = read_table(warehouse_setup.settings, "marts.mart_rhine_level")
    mart = mart.set_index(pd.to_datetime(mart["date"]))
    assert bool(mart.loc[pd.Timestamp("2026-11-17"), "below_glw"])  # 61 < 77
    assert not bool(mart.loc[pd.Timestamp("2026-11-18"), "below_glw"])
    assert mart["glw_cm"].iloc[0] == 77.0 and mart["mw_cm"].iloc[0] == 208.0
