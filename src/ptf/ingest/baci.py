"""Download CEPII BACI (reconciled bilateral trade at HS6 level) into the raw layer.

BACI is published as one zip file per HS revision and version (HS17, V202601: ~800 MB) with
one CSV per year plus country and product code lists. The zip is downloaded once and kept
unchanged in `data/raw/baci/`; the clean step reads the CSVs directly from it. Keeping the
zip allows extracting other products later (e.g. crude oil, LNG) without a new download.
"""

import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

CHUNK_BYTES = 8 * 1024 * 1024


def baci_zip_path(raw_dir: Path, hs_revision: str, version: str) -> Path:
    return raw_dir / "baci" / f"BACI_{hs_revision}_V{version}.zip"


def ingest_baci(
    raw_dir: Path,
    url: str,
    hs_revision: str,
    version: str,
    session: requests.Session | None = None,
) -> Path:
    """Download the zip unless it is already there; returns its path.

    Streams to a `.part` file and renames it only when the size matches the server's
    Content-Length, so an interrupted download never looks complete.
    """
    path = baci_zip_path(raw_dir, hs_revision, version)
    if path.exists():
        return path
    session = session or requests.Session()
    partial = path.with_suffix(".zip.part")
    path.parent.mkdir(parents=True, exist_ok=True)

    with session.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        expected = int(response.headers.get("Content-Length", 0))
        written = 0
        with partial.open("wb") as file:
            for chunk in response.iter_content(CHUNK_BYTES):
                file.write(chunk)
                written += len(chunk)

    if expected and written != expected:
        raise OSError(f"BACI download incomplete: {written} of {expected} bytes")
    partial.rename(path)
    logger.info("BACI %s V%s downloaded: %.0f MB -> %s", hs_revision, version, written / 1e6, path)
    return path
