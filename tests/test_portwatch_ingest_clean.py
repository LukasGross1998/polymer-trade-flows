"""PortWatch ingest (paging, incremental updates) and cleaning. No live API."""

import json
from pathlib import Path

import pandas as pd
from test_ingest_comtrade import FakeResponse, FakeSession, no_sleep

from ptf.clean.portwatch import (
    EVENT_COLUMNS,
    TRANSIT_COLUMNS,
    clean_events,
    clean_port_activity,
    clean_transits,
)
from ptf.ingest import portwatch

FIXTURES = Path(__file__).parent / "fixtures"


def sample_features() -> list[dict]:
    """18 real rows: Suez, Bab el-Mandeb and Cape of Good Hope, 2026-11-03 to 2026-11-08."""
    return json.loads((FIXTURES / "portwatch_daily_sample.json").read_text())["features"]


def page(features: list[dict], more: bool) -> FakeResponse:
    payload = {"features": features}
    if more:
        payload["exceededTransferLimit"] = True
    return FakeResponse(200, payload)


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


def test_clean_keeps_latest_revision_per_day(tmp_path: Path) -> None:
    features = sample_features()
    portwatch.ingest_chokepoint_transits(
        tmp_path, session=FakeSession([page(features, more=False)]), sleep=no_sleep
    )
    # A later download revises Suez on 2026-11-08 from its first value to 99 transits.
    revised = json.loads(json.dumps(features[-3:]))
    for feature in revised:
        if feature["attributes"]["portid"] == "chokepoint1":
            feature["attributes"]["n_total"] = 99
    portwatch.ingest_chokepoint_transits(
        tmp_path, session=FakeSession([page(revised, more=False)]), sleep=no_sleep
    )

    transits = clean_transits(tmp_path)

    assert list(transits.columns) == TRANSIT_COLUMNS
    assert len(transits) == 18  # duplicates removed
    suez = transits[(transits["chokepoint"] == "Suez Canal") & (transits["date"] == "2026-11-08")]
    assert suez["n_total"].tolist() == [99]


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
    ports = clean_port_activity(tmp_path, {"p1": "Port One", "p2": "Port Two"})
    assert sorted(ports["port"].unique()) == ["Port One", "Port Two"]
    assert len(ports) == 3


def test_events_get_dates_from_epoch_milliseconds(tmp_path: Path) -> None:
    event = {
        "eventid": 1,
        "eventtype": "OT",
        "eventname": "HORMUZ-26",
        "alertlevel": "RED",
        "country": None,
        "fromdate": 1772323200000,  # 2026-03-01 00:00 UTC
        "todate": None,
        "lat": 26.3,
        "long": 56.9,
        "affectedports": "chokepoint6",
        "n_affectedports": 1,
        "htmldescription": "Trade Disruptions in the Strait of Hormuz",
    }
    portwatch.ingest_events(
        tmp_path, session=FakeSession([page([{"attributes": event}], more=False)]), sleep=no_sleep
    )

    events = clean_events(tmp_path)

    assert list(events.columns) == EVENT_COLUMNS
    assert str(events.loc[0, "from_date"].date()) == "2026-03-01"
    assert pd.isna(events.loc[0, "to_date"])  # still ongoing
