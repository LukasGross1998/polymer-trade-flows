"""EU import duties per polyethylene grade from the World Bank WITS API (TRAINS; spec 009).

WITS answers in SDMX XML: one observation per reporter, partner, product and year with the
MFN (most-favoured-nation, i.e. third-country) rate. For an HS6 code the EU has several
tariff lines (8-digit CN codes); WITS gives their simple average, minimum and maximum.
Example HDPE 390120, 2023: lines at 0 % and 6.5 % -> average 3.25 %. The landed cost uses the
maximum, the rate of the ordinary pellets (the 0 % line covers special forms).

Raw layer: the XML answers of each download in their own folder, never overwritten; the
newest download is parsed into `wits/landing_eu_duty.parquet` for dbt.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

URL = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN/reporter/{reporter}"
    "/partner/000/product/{hs6}/year/{year}/datatype/reported"
)
COLUMNS = ["reporter", "hs6", "year", "tariff_type", "avg_pct", "min_pct", "max_pct", "lines"]


def wits_dir(raw_dir: Path) -> Path:
    return raw_dir / "wits"


def parse_mfn(xml_text: str) -> list[dict[str, float | int | str | None]]:
    """Observations of a WITS TRAINS answer; [] for "NoRecordsFound" or an empty answer."""
    if "<" not in xml_text:
        return []
    rows: list[dict[str, float | int | str | None]] = []
    for element in ET.fromstring(xml_text).iter():
        if not element.tag.endswith("Series"):
            continue
        for obs in element:
            if not obs.tag.endswith("Obs"):
                continue
            rows.append(
                {
                    "reporter": element.get("REPORTER"),
                    "hs6": element.get("PRODUCTCODE"),
                    "year": int(obs.get("TIME_PERIOD", "0")),
                    "tariff_type": obs.get("TARIFFTYPE"),
                    "avg_pct": float(obs.get("OBS_VALUE", "nan")),
                    "min_pct": float(obs.get("MIN_RATE", "nan")),
                    "max_pct": float(obs.get("MAX_RATE", "nan")),
                    "lines": int(obs.get("TOTALNOOFLINES", "0")),
                }
            )
    return rows


def ingest_duties(
    raw_dir: Path,
    reporter: str,
    hs6_codes: list[str],
    years_back: int,
    session: requests.Session | None = None,
    today: datetime | None = None,
) -> Path:
    """Newest MFN rate per grade: try last year, then earlier years; store every answer."""
    now = today or datetime.now(UTC)
    session = session or requests.Session()
    folder = wits_dir(raw_dir) / f"{now:%Y%m%dT%H%M%S%f}"
    if folder.exists():
        raise FileExistsError(f"raw files are never overwritten: {folder}")
    folder.mkdir(parents=True)
    for hs6 in hs6_codes:
        for year in range(now.year - 1, now.year - 1 - years_back, -1):
            response = session.get(URL.format(reporter=reporter, hs6=hs6, year=year), timeout=60)
            text = response.text if response.status_code == 200 else ""
            (folder / f"{hs6}_{year}.xml").write_text(text, encoding="utf-8")
            if parse_mfn(text):
                break
    logger.info("WITS duties for %s grades written to %s", len(hs6_codes), folder)
    return folder


def write_duty_landing(raw_dir: Path) -> Path:
    """Parse the newest download into `landing_eu_duty.parquet`; empty without a download.

    Always writes the file, so the dbt models build before the first WITS download.
    """
    folders = sorted(p for p in wits_dir(raw_dir).glob("*") if p.is_dir())
    rows: list[dict[str, float | int | str | None]] = []
    if folders:
        for path in sorted(folders[-1].glob("*.xml")):
            rows += parse_mfn(path.read_text(encoding="utf-8"))
    landing = pd.DataFrame(rows, columns=COLUMNS)
    if not landing.empty:  # per grade only the newest year found
        landing = landing.sort_values("year").groupby("hs6", as_index=False).tail(1)
    path = wits_dir(raw_dir) / "landing_eu_duty.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    landing.astype({"year": "int64", "lines": "int64"}).to_parquet(path, index=False)
    return path
