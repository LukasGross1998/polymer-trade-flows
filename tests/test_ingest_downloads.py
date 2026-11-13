"""File downloads (BACI zip, NY Fed GSCPI): caching and protection against partial files."""

from pathlib import Path

import pytest
import requests
from helpers import FakeResponse, FakeSession

from ptf.ingest import baci, gscpi


class TruncatedResponse(FakeResponse):
    """Announces more bytes in Content-Length than it delivers: a broken connection."""

    def __init__(self, content: bytes, announced: int) -> None:
        super().__init__(200, content=content)
        self.headers = {"Content-Length": str(announced)}


def test_baci_download_is_written_once_and_cached(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, content=b"zip-bytes" * 1000)])

    path = baci.ingest_baci(tmp_path, "url", "HS17", "202601", session=session)
    again = baci.ingest_baci(tmp_path, "url", "HS17", "202601", session=FakeSession([]))

    assert path == again == tmp_path / "baci" / "BACI_HS17_V202601.zip"
    assert path.read_bytes() == b"zip-bytes" * 1000
    assert not path.with_suffix(".zip.part").exists()


def test_incomplete_baci_download_never_looks_complete(tmp_path: Path) -> None:
    session = FakeSession([TruncatedResponse(b"half", announced=8)])

    with pytest.raises(OSError, match="incomplete"):
        baci.ingest_baci(tmp_path, "url", "HS17", "202601", session=session)

    assert not baci.baci_zip_path(tmp_path, "HS17", "202601").exists()


def test_baci_http_error_is_raised(tmp_path: Path) -> None:
    with pytest.raises(requests.HTTPError):
        baci.ingest_baci(
            tmp_path, "url", "HS17", "202601", session=FakeSession([FakeResponse(404)])
        )


def test_gscpi_download_is_cached_while_fresh(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, content=b"xls-bytes")])

    first = gscpi.ingest_gscpi(tmp_path, "url", max_age_days=1, session=session)
    second = gscpi.ingest_gscpi(tmp_path, "url", max_age_days=1, session=session)

    assert first is not None and first.suffix == ".xls"
    assert second is None  # still fresh: no second request
    assert len(session.calls) == 1
    assert gscpi.latest_gscpi(tmp_path) == first
