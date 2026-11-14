"""EU duties from WITS (spec 009): parsing a saved real answer and the download order."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from helpers import FIXTURES, FakeResponse

from ptf.trade import duties

ANSWER = (FIXTURES / "wits_eu_390110_2022.xml").read_text(encoding="utf-8")


def test_parse_saved_answer() -> None:
    (row,) = duties.parse_mfn(ANSWER)

    assert (row["hs6"], row["year"], row["tariff_type"]) == ("390110", 2022, "MFN")
    assert (row["avg_pct"], row["max_pct"], row["lines"]) == (6.5, 6.5, 2)
    assert duties.parse_mfn("Not Found - NoRecordsFound") == []


class TextSession:
    """Answers "no records" until the given year, then the saved answer."""

    def __init__(self, hit_year: int) -> None:
        self.hit_year = hit_year
        self.urls: list[str] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.urls.append(url)
        response = FakeResponse(200)
        response.text = ANSWER if f"/year/{self.hit_year}/" in url else "Not Found - NoRecordsFound"  # type: ignore[attr-defined]
        return response


def test_tries_newest_year_first_and_stops_at_a_hit(tmp_path: Path) -> None:
    session = TextSession(hit_year=2022)

    duties.ingest_duties(
        tmp_path,
        "918",
        ["390110"],
        6,
        session=session,
        today=datetime(2026, 11, 14, tzinfo=UTC),  # type: ignore[arg-type]
    )
    landing = pd.read_parquet(duties.write_duty_landing(tmp_path))

    assert [u.split("/year/")[1][:4] for u in session.urls] == ["2025", "2024", "2023", "2022"]
    assert landing[["hs6", "year", "max_pct"]].values.tolist() == [["390110", 2022, 6.5]]


def test_landing_is_written_empty_before_the_first_download(tmp_path: Path) -> None:
    landing = pd.read_parquet(duties.write_duty_landing(tmp_path))

    assert landing.empty and list(landing.columns) == duties.COLUMNS
