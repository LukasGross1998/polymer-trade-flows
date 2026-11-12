"""PortWatch ingest (paging, incremental updates) and cleaning. No live API."""

import json
from pathlib import Path

import pandas as pd
from test_ingest_comtrade import FakeResponse, FakeSession, no_sleep

from ptf.clean.portwatch import TRANSIT_COLUMNS, clean_transits
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
