"""PortWatch ingest (paging, incremental updates). Cleaning is tested on the dbt marts."""

import json
from pathlib import Path

import pandas as pd
from helpers import FakeSession, no_sleep
from helpers import arcgis_page as page

from ptf.ingest import portwatch

FIXTURES = Path(__file__).parent / "fixtures"


def sample_features() -> list[dict]:
    """18 real rows: Suez, Bab el-Mandeb and Cape of Good Hope, 2026-11-03 to 2026-11-08."""
    return json.loads((FIXTURES / "portwatch_daily_sample.json").read_text())["features"]


def test_query_all_follows_pages_until_limit_not_exceeded() -> None:
    features = sample_features()
    session = FakeSession([page(features[:10], more=True), page(features[10:], more=False)])

    rows = portwatch.query_all(session, "url", "1=1", "*", "date", sleep=no_sleep)

    assert len(rows) == 18
    assert [c["params"]["resultOffset"] for c in session.calls] == [0, 10]


def test_first_download_fetches_everything(tmp_path: Path) -> None:
    session = FakeSession([page(sample_features(), more=False)])

    path = portwatch.ingest_chokepoint_transits(tmp_path, session=session, sleep=no_sleep)

    assert session.calls[0]["params"]["where"] == "1=1"
    assert len(pd.read_parquet(path)) == 18
    assert str(portwatch.last_stored_date(tmp_path)) == "2026-11-08"


def test_update_refetches_revision_window_only(tmp_path: Path) -> None:
    portwatch.ingest_chokepoint_transits(
        tmp_path, session=FakeSession([page(sample_features(), more=False)]), sleep=no_sleep
    )
    session = FakeSession([page([], more=False)])

    result = portwatch.ingest_chokepoint_transits(
        tmp_path, revision_days=14, session=session, sleep=no_sleep
    )

    assert session.calls[0]["params"]["where"] == "date >= DATE '2026-10-25'"  # 11-08 minus 14
    assert result is None  # nothing new: no file written


def port_row(port_id: str, day: str, portcalls: int) -> dict:
    row = {"date": day, "portid": port_id, "portname": port_id, "portcalls": portcalls}
    for column in ["portcalls_tanker", "portcalls_container", "import", "export"]:
        row[column] = 0
    return {"attributes": row}


def test_port_activity_fetches_history_only_for_new_ports(tmp_path: Path) -> None:
    first = FakeSession([page([port_row("p1", "2026-11-01", 5)], more=False)])
    portwatch.ingest_port_activity(tmp_path, ["p1"], session=first, sleep=no_sleep)

    # p2 is added to the configuration later: full history for p2, update window for p1.
    second = FakeSession(
        [
            page([port_row("p2", "2019-01-01", 7)], more=False),
            page([port_row("p1", "2026-11-02", 6)], more=False),
        ]
    )
    portwatch.ingest_port_activity(tmp_path, ["p1", "p2"], session=second, sleep=no_sleep)

    wheres = [call["params"]["where"] for call in second.calls]
    assert wheres == [
        "portid IN ('p2')",
        "portid IN ('p1') AND date >= DATE '2026-10-18'",
    ]


def test_country_trade_is_incremental(tmp_path: Path) -> None:
    row = {"ISO3": "SAU", "country": "Saudi Arabia", "date": "2026-11-06", "import": 1, "export": 2}
    for flow in ("import", "export"):
        for kind in portwatch.TRADE_TYPES:
            row[f"{flow}_{kind}"] = 0
    portwatch.ingest_country_trade(
        tmp_path, session=FakeSession([page([{"attributes": row}], more=False)]), sleep=no_sleep
    )
    second = FakeSession([page([], more=False)])
    portwatch.ingest_country_trade(tmp_path, session=second, sleep=no_sleep)

    assert second.calls[0]["params"]["where"] == "date >= DATE '2026-10-23'"


def test_port_links_are_downloaded_once(tmp_path: Path) -> None:
    def link(src: str, dst: str, capacity: float) -> dict:
        return {
            "attributes": {
                "from_portid": src,
                "from_portname": src,
                "from_country": "X",
                "from_lat": 0.0,
                "from_lon": 0.0,
                "to_portid": dst,
                "to_portname": dst,
                "to_country": "Y",
                "to_lat": 1.0,
                "to_lon": 1.0,
                "average_transit_days": 3.0,
                "daily_capacity_at_risk": capacity,
            }
        }

    session = FakeSession([page([link("a", "b", 2000.0), link("a", "a", 5000.0)], more=False)])
    portwatch.ingest_port_links(tmp_path, 1000, session=session, sleep=no_sleep)
    portwatch.ingest_port_links(tmp_path, 1000, session=FakeSession([]), sleep=no_sleep)  # cached

    assert session.calls[0]["params"]["where"] == "daily_capacity_at_risk >= 1000"
