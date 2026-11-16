"""Market data ingest (FRED, GSCPI). The cleaning is tested on the dbt marts. No live API."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from helpers import REPO_ROOT

from ptf.markets import fred
from ptf.markets.config import load_market_config
from ptf.markets.gscpi import tidy_gscpi

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
    config = load_market_config(REPO_ROOT / "config" / "markets.yaml")

    assert "DCOILBRENTEU" in {s.id for s in config.fred_series}
    assert config.key_events[0].label.startswith("Red Sea")


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


def test_polymer_over_crude_spread() -> None:
    from ptf.markets import indicators

    dates = pd.to_datetime(["2026-11-09", "2026-11-10", "2026-11-16"])
    lldpe = pd.DataFrame({"date": dates, "value": [1200.0, 1210.0, 1220.0]})
    # Brent on 6 and 10 Nov only; 16 Nov is more than 4 days after the last Brent value.
    brent = pd.DataFrame({"date": pd.to_datetime(["2026-11-06", "2026-11-10"]), "value": [80, 82]})
    gap = indicators.spread(lldpe, indicators.per_tonne(brent, 7.32))

    # 1,200 − 80 x 7.32 = 614.4 (Brent of 6 Nov, 3 days earlier); 1,210 − 82 x 7.32 = 609.76.
    assert gap["value"].round(2).tolist() == [614.4, 609.76]
    assert gap["date"].max() == pd.Timestamp("2026-11-10")
