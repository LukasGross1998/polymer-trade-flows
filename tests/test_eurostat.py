"""Eurostat monthly price indices (spec 019) with a fake JSON-stat answer."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ptf.markets import eurostat
from ptf.markets.config import EurostatSeries

ANSWER = {
    "id": ["freq", "geo", "time"],
    "size": [1, 1, 2],
    "dimension": {
        "freq": {"category": {"index": {"M": 0}}},
        "geo": {"category": {"index": {"EU27_2020": 0}}},
        "time": {"category": {"index": {"2026-08": 0, "2026-09": 1}}},
    },
    "value": {"0": 112.0, "1": 113.3},
}
SERIES = EurostatSeries(
    id="EU_PPI_PLASTICS",
    dataset="sts_inpp_m",
    filters={"geo": "EU27_2020", "nace_r2": "C2016"},
    name="EU producer prices, plastics",
    unit="index 2021=100",
)


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, params: dict[str, str], timeout: int) -> object:
        self.calls.append((url, params))
        return type("R", (), {"text": json.dumps(ANSWER), "raise_for_status": lambda self: None})()


def test_parse_months_to_dates() -> None:
    table = eurostat.parse(ANSWER, "EU_PPI_PLASTICS")
    assert table["date"].tolist() == [pd.Timestamp("2026-08-01"), pd.Timestamp("2026-09-01")]
    assert table["value"].tolist() == [112.0, 113.3]
    assert eurostat.parse({"id": [], "size": [], "dimension": {}}, "X").empty


def test_ingest_and_landing(tmp_path: Path) -> None:
    session = FakeSession()
    eurostat.ingest_eurostat(
        tmp_path,
        [SERIES],
        session=session,  # type: ignore[arg-type]
        today=datetime(2026, 11, 19, tzinfo=UTC),
    )
    url, params = session.calls[0]
    assert url.endswith("/sts_inpp_m") and params["nace_r2"] == "C2016"
    landing = pd.read_parquet(eurostat.write_landing(tmp_path))
    assert set(landing["series_id"]) == {"EU_PPI_PLASTICS"} and len(landing) == 2


def test_empty_landing_before_the_first_download(tmp_path: Path) -> None:
    assert pd.read_parquet(eurostat.write_landing(tmp_path)).empty
