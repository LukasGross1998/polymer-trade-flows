from pathlib import Path

import pytest

from ptf.clean.brent import annual_brent, parse_brent_csv
from ptf.ingest.brent import ingest_brent

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_drops_days_without_quote() -> None:
    daily = parse_brent_csv(FIXTURES / "brent_sample.csv")

    assert list(daily.columns) == ["date", "usd_per_bbl"]
    assert len(daily) == 4  # the empty and the "." day are dropped


def test_annual_brent_averages_per_year() -> None:
    annual = annual_brent(parse_brent_csv(FIXTURES / "brent_sample.csv")).set_index("year")

    assert annual.loc[2023, "brent_usd_per_bbl"] == pytest.approx(78.0)
    assert annual.loc[2024, "brent_usd_per_bbl"] == pytest.approx(77.0)
    assert annual.loc[2024, "quoted_days"] == 2


class FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url: str, params: dict, timeout: int) -> "FakeSession":
        self.calls += 1
        return self

    content = b"observation_date,DCOILBRENTEU\n2024-01-02,76.00\n"

    def raise_for_status(self) -> None:
        pass


def test_ingest_brent_stores_csv_unchanged_and_caches(tmp_path: Path) -> None:
    session = FakeSession()

    path = ingest_brent(tmp_path, session=session)
    ingest_brent(tmp_path, session=session)  # second call hits the cache

    assert path.read_bytes() == FakeSession.content
    assert session.calls == 1
