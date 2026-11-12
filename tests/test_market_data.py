"""Market data: FRED and GSCPI ingest and cleaning, Brent annual averages. No live API."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from conftest import REPO_ROOT

from ptf.clean.brent import annual_brent
from ptf.clean.market import MARKET_COLUMNS, clean_market_series, parse_fred_csv, tidy_gscpi
from ptf.ingest import fred
from ptf.market_config import SeriesConfig, load_market_config

FIXTURES = Path(__file__).parent / "fixtures"
CSV = b"observation_date,DCOILBRENTEU\n2024-01-02,76.00\n2024-01-03,.\n2024-01-04,78.00\n"


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get(self, url: str, params: dict | None = None, timeout: int = 0) -> "FakeSession":
        self.calls.append(params or {})
        return self

    content = CSV

    def raise_for_status(self) -> None:
        pass


def test_project_market_config_is_valid() -> None:
    config = load_market_config(REPO_ROOT / "config" / "market_data.yaml")

    assert "DCOILBRENTEU" in {s.id for s in config.fred_series}
    assert config.key_events[0].label.startswith("Red Sea")


def test_parse_fred_drops_days_without_quote() -> None:
    daily = parse_fred_csv(FIXTURES / "brent_sample.csv")

    assert list(daily.columns) == ["date", "value"]
    assert len(daily) == 4  # the empty and the "." day are dropped


def test_annual_brent_averages_per_year() -> None:
    daily = parse_fred_csv(FIXTURES / "brent_sample.csv").rename(columns={"value": "usd_per_bbl"})

    annual = annual_brent(daily).set_index("year")

    assert annual.loc[2023, "brent_usd_per_bbl"] == pytest.approx(78.0)
    assert annual.loc[2024, "quoted_days"] == 2


def test_fred_downloads_only_stale_series(tmp_path: Path) -> None:
    session = FakeSession()

    fred.ingest_fred(tmp_path, ["DCOILBRENTEU"], max_age_days=1, session=session)
    fred.ingest_fred(tmp_path, ["DCOILBRENTEU"], max_age_days=1, session=session)  # fresh

    assert session.calls == [{"id": "DCOILBRENTEU"}]
    assert fred.latest_raw(tmp_path, "DCOILBRENTEU").read_bytes() == CSV


def test_freshness_uses_download_time_from_file_name() -> None:
    path = Path("20261110T120000000000.csv")
    now = datetime(2026, 11, 12, tzinfo=UTC)

    assert fred.is_fresh(path, max_age_days=3, now=now)
    assert not fred.is_fresh(path, max_age_days=1, now=now)
    assert not fred.is_fresh(None, max_age_days=1, now=now)


def test_gscpi_sheet_skips_header_and_empty_rows() -> None:
    sheet = pd.DataFrame(
        [["Date", "GSCPI"], [None, None], ["31-Jan-1998", -1.18], ["31-Oct-2026", 1.26]]
    )

    gscpi = tidy_gscpi(sheet)

    assert gscpi["date"].dt.strftime("%Y-%m").tolist() == ["1998-01", "2026-10"]
    assert gscpi["value"].tolist() == [-1.18, 1.26]


def test_clean_market_series_is_long_table(tmp_path: Path) -> None:
    fred.ingest_fred(tmp_path, ["DCOILBRENTEU"], session=FakeSession())
    series = [
        SeriesConfig(
            id="DCOILBRENTEU", name="Brent", unit="USD/bbl", frequency="daily", group="energy"
        )
    ]

    market = clean_market_series(tmp_path, series)

    assert list(market.columns) == MARKET_COLUMNS
    assert market["value"].tolist() == [76.0, 78.0]
    assert set(market["series_id"]) == {"DCOILBRENTEU"}
