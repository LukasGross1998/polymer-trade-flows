"""Eurostat Comext monthly imports (spec 019) with a fake JSON-stat answer."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from ptf.core import jsonstat
from ptf.trade import comext, steps
from ptf.trade.config import ComextConfig

# Two partners (US, AT) x two indicators x two months, row-major over the dimensions.
ANSWER = {
    "id": ["freq", "reporter", "partner", "product", "flow", "indicators", "time"],
    "size": [1, 1, 2, 1, 1, 2, 2],
    "dimension": {
        "freq": {"category": {"index": {"M": 0}}},
        "reporter": {"category": {"index": {"EU27_2020": 0}}},
        "partner": {"category": {"index": {"US": 0, "AT": 1}}},
        "product": {"category": {"index": {"390120": 0}}},
        "flow": {"category": {"index": {"1": 0}}},
        "indicators": {"category": {"index": {"VALUE_IN_EUROS": 0, "QUANTITY_IN_100KG": 1}}},
        "time": {"category": {"index": {"2026-08": 0, "2026-09": 1}}},
    },
    # US value Aug, Sep; US quantity Aug, Sep; AT value Aug (Sep missing), AT quantity Aug.
    "value": {"0": 1_150_000, "1": 1_200_000, "2": 10_000, "3": 12_000, "4": 50_000, "6": 400},
}


def test_jsonstat_positions_follow_the_dimension_order() -> None:
    cells = {(c["partner"], c["indicators"], c["time"]): c["value"] for c in jsonstat.rows(ANSWER)}
    assert cells[("US", "QUANTITY_IN_100KG", "2026-09")] == 12_000
    assert cells[("AT", "VALUE_IN_EUROS", "2026-08")] == 50_000
    assert ("AT", "VALUE_IN_EUROS", "2026-09") not in cells  # missing cell skipped


def test_parse_gives_one_row_per_month_partner_grade() -> None:
    table = comext.parse(ANSWER).set_index(["partner_iso2", "month"])
    # 1,000 t for 1.15 m EUR -> 1,150 EUR/t CIF (spec 019).
    assert table.loc[("US", "2026-08"), "value_eur"] == 1_150_000
    assert table.loc[("US", "2026-08"), "qty_100kg"] / 10 == 1000


class FakeSession:
    def __init__(self) -> None:
        self.params: list[dict[str, object]] = []

    def get(self, url: str, params: dict[str, object], timeout: int) -> object:
        self.params.append(params)
        return type("R", (), {"text": json.dumps(ANSWER), "raise_for_status": lambda self: None})()


def test_ingest_and_landing_drop_intra_eu(tmp_path: Path) -> None:
    session = FakeSession()
    folder = comext.ingest_comext(
        tmp_path,
        ["390120"],
        "2024-01",
        session=session,  # type: ignore[arg-type]
        today=datetime(2026, 11, 19, tzinfo=UTC),
    )
    assert session.params[0]["sinceTimePeriod"] == "2024-01"
    assert (folder / "390120.json").exists()
    with pytest.raises(FileExistsError):
        comext.ingest_comext(
            tmp_path,
            ["390120"],
            "2024-01",
            session=session,  # type: ignore[arg-type]
            today=datetime(2026, 11, 19, tzinfo=UTC),
        )

    landing = pd.read_parquet(comext.write_landing(tmp_path, ["AT"]))
    assert set(landing["partner_iso2"]) == {"US"}  # Austria is an EU member
    assert len(landing) == 2


def test_empty_landing_before_the_first_download(tmp_path: Path) -> None:
    landing = pd.read_parquet(comext.write_landing(tmp_path, ["AT"]))
    assert landing.empty and list(landing.columns) == comext.COLUMNS


def test_download_starts_in_january_of_the_year_before_last() -> None:
    from datetime import date

    assert steps.comext_start(ComextConfig(years_back=2), date(2026, 11, 19)) == "2024-01"
