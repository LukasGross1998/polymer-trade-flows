"""Download CEPII BACI (reconciled bilateral trade at HS6 level) and unpack it for the warehouse.

BACI is published as one zip file per HS revision and version (HS17, V202601: ~800 MB) with
one CSV per year plus country and product code lists. The zip is downloaded once and kept
unchanged in `data/raw/baci/`; the clean step reads the CSVs directly from it. Keeping the
zip allows extracting other products later (e.g. crude oil, LNG) without a new download.
"""

import io
import logging
import re
import zipfile
from pathlib import Path

import pandas as pd
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


# --- landing: unpack the product group from the zip for the warehouse (ADR-011) ------------

CHUNK_ROWS = 2_000_000


def landing_dir(raw_dir: Path) -> Path:
    return raw_dir / "baci"


def _member(archive: zipfile.ZipFile, pattern: str) -> str:
    """Name of the single zip member matching `pattern` (regular expression)."""
    matches = [name for name in archive.namelist() if re.search(pattern, name)]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one file matching {pattern!r} in BACI zip, got {matches}"
        )
    return matches[0]


def _read_year(archive: zipfile.ZipFile, name: str, hs_prefix: str) -> pd.DataFrame:
    """One yearly CSV, filtered to `hs_prefix` while reading in chunks (~10 m rows per year).

    Values stay as published: `v` in thousand USD, `q` in tonnes ("NA" -> missing).
    """
    parts = []
    with archive.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8")
        for chunk in pd.read_csv(text, dtype=str, chunksize=CHUNK_ROWS):
            chunk.columns = [c.strip() for c in chunk.columns]
            parts.append(chunk[chunk["k"].str.strip().str.startswith(hs_prefix)])
    flows = pd.concat(parts, ignore_index=True)
    return pd.DataFrame(
        {
            "year": flows["t"].astype(int),
            "exporter_code": flows["i"].astype(int),
            "importer_code": flows["j"].astype(int),
            "hs6": flows["k"].str.strip(),
            "value_kusd": pd.to_numeric(flows["v"].str.strip(), errors="coerce"),
            "qty_t": pd.to_numeric(flows["q"].str.strip(), errors="coerce"),
        }
    )


def write_landing(zip_path: Path, years: list[int], hs_prefix: str, raw_dir: Path) -> list[Path]:
    """Unpack the flows of one product group and BACI's code lists to Parquet.

    Writes `landing_hs{prefix}.parquet` (flows, unchanged values), `landing_country_codes`
    and `landing_product_codes`. Years missing in the zip are skipped with a warning.
    These files are the dbt sources; everything else happens in SQL.
    """
    folder = landing_dir(raw_dir)
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        flows = []
        for year in years:
            matches = [n for n in names if re.search(rf"_Y{year}_V\d+\.csv$", n)]
            if not matches:
                logger.warning("BACI zip has no data for %s; skipped", year)
                continue
            flows.append(_read_year(archive, matches[0], hs_prefix))
        with archive.open(_member(archive, r"country_codes.*\.csv$")) as file:
            countries = pd.read_csv(file, dtype=str, keep_default_na=False)
        with archive.open(_member(archive, r"product_codes.*\.csv$")) as file:
            products = pd.read_csv(file, dtype=str, keep_default_na=False)

    paths = [
        folder / f"landing_hs{hs_prefix}.parquet",
        folder / "landing_country_codes.parquet",
        folder / "landing_product_codes.parquet",
    ]
    pd.concat(flows, ignore_index=True).to_parquet(paths[0], index=False)
    countries.to_parquet(paths[1], index=False)
    products[products["code"].str.startswith(hs_prefix)].to_parquet(paths[2], index=False)
    logger.info("BACI landing written to %s", folder)
    return paths
