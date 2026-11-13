"""Comtrade ingest tests. No live API: HTTP is replaced by a fake session with canned replies."""

import json
from pathlib import Path

import pandas as pd
import pytest
import requests
from helpers import FakeResponse, FakeSession, no_sleep

from ptf.legacy.comtrade import ingest as comtrade

FIXTURES = Path(__file__).parent / "fixtures"


def deu_payload() -> dict:
    return json.loads((FIXTURES / "comtrade_deu_2023.json").read_text())


def test_build_params_requests_totals_only() -> None:
    params = comtrade.build_params(276, 2023, "3901", "M,X")

    assert params["reporterCode"] == 276
    assert params["period"] == 2023
    assert params["partner2Code"] == 0
    assert params["customsCode"] == "C00"
    assert params["motCode"] == 0


def test_get_json_retries_on_429_with_growing_waits() -> None:
    session = FakeSession([FakeResponse(429), FakeResponse(429), FakeResponse(200, {"ok": 1})])
    waits: list[float] = []

    result = comtrade.get_json(session, "url", sleep=waits.append, base_wait_seconds=2.0)

    assert result == {"ok": 1}
    assert waits == [2.0, 4.0]


def test_get_json_gives_up_after_max_retries() -> None:
    session = FakeSession([FakeResponse(429)] * 3)

    with pytest.raises(requests.HTTPError):
        comtrade.get_json(session, "url", max_retries=2, sleep=no_sleep)
    assert len(session.calls) == 3


def test_get_json_does_not_retry_client_errors() -> None:
    session = FakeSession([FakeResponse(400)])

    with pytest.raises(requests.HTTPError):
        comtrade.get_json(session, "url", sleep=no_sleep)
    assert len(session.calls) == 1


def test_fetch_reporter_year_returns_raw_records_with_timestamp() -> None:
    session = FakeSession([FakeResponse(200, deu_payload())])

    raw = comtrade.fetch_reporter_year(session, 276, 2023, "3901", sleep=no_sleep)

    assert len(raw) == 12
    assert "fetched_at" in raw.columns
    # Raw data is kept unchanged: original Comtrade column names and units (kg).
    assert {"reporterCode", "partnerCode", "flowCode", "netWgt", "primaryValue"} <= set(raw)


def test_truncated_response_is_split_by_flow() -> None:
    full = {"data": [{"flowCode": "M"}] * comtrade.MAX_RECORDS}
    imports = {"data": [{"flowCode": "M"}] * 300}
    exports = {"data": [{"flowCode": "X"}] * 250}
    session = FakeSession([FakeResponse(200, p) for p in (full, imports, exports)])

    raw = comtrade.fetch_reporter_year(session, 156, 2023, "3901", sleep=no_sleep)

    assert len(raw) == 550
    assert [c["params"]["flowCode"] for c in session.calls] == ["M,X", "M", "X"]


def test_ingest_writes_parquet_and_uses_cache(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, deu_payload())])

    written = comtrade.ingest_comtrade(
        {"DEU": 276}, [2023], "3901", tmp_path, session=session, sleep=no_sleep
    )

    assert written == [tmp_path / "comtrade" / "DEU_2023.parquet"]
    assert len(pd.read_parquet(written[0])) == 12

    # Second run: file exists, so no HTTP request is made at all.
    again = comtrade.ingest_comtrade(
        {"DEU": 276}, [2023], "3901", tmp_path, session=FakeSession([]), sleep=no_sleep
    )
    assert again == []


def test_empty_response_is_cached_as_empty_file(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, {"count": 0, "data": [], "error": ""})])

    written = comtrade.ingest_comtrade(
        {"IRN": 364}, [2024], "3901", tmp_path, session=session, sleep=no_sleep
    )

    assert pd.read_parquet(written[0]).empty


def test_reporter_codes_skip_historic_entries_and_non_reporters() -> None:
    reference = pd.DataFrame(json.loads((FIXTURES / "reporters.json").read_text())["results"])

    codes = comtrade.reporter_codes(reference, ["DEU", "USA", "TWN"])

    assert codes == {"DEU": 276, "USA": 842}


def test_quota_exceeded_stops_download_but_keeps_cached_files(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, deu_payload()), FakeResponse(403)])

    written = comtrade.ingest_comtrade(
        {"DEU": 276}, [2023, 2024], "3901", tmp_path, session=session, sleep=no_sleep
    )

    assert written == [tmp_path / "comtrade" / "DEU_2023.parquet"]
    assert len(session.calls) == 2  # 403 is not retried
