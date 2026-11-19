"""Monthly EU price indices from the Eurostat dissemination API (spec 019).

Each configured series is one Eurostat dataset with fixed filters, e.g. the EU27 producer
price index of plastics in primary forms (`sts_inpp_m`, NACE C20.16, 2021 = 100). Free reuse
with attribution (Eurostat copyright notice, Decision 2011/833/EU); no key.

Raw layer: one JSON answer per series and download, never overwritten; the newest answers
are parsed into `eurostat/landing_eurostat.parquet` (date, series_id, value) for dbt.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from ptf.core import jsonstat
from ptf.markets.config import EurostatSeries

logger = logging.getLogger(__name__)

URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"
COLUMNS = ["date", "series_id", "value"]


def eurostat_dir(raw_dir: Path) -> Path:
    return raw_dir / "eurostat"


def parse(answer: dict[str, object], series_id: str) -> pd.DataFrame:
    """date (first day of the month), series_id, value from one JSON-stat answer."""
    cells = jsonstat.rows(answer) if "value" in answer else []
    if not cells:
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.DataFrame(cells)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(frame["time"], format="%Y-%m"),
            "series_id": series_id,
            "value": frame["value"].astype(float),
        }
    ).sort_values("date")[COLUMNS]


def ingest_eurostat(
    raw_dir: Path,
    series: list[EurostatSeries],
    session: requests.Session | None = None,
    today: datetime | None = None,
) -> Path:
    now = today or datetime.now(UTC)
    session = session or requests.Session()
    folder = eurostat_dir(raw_dir) / f"{now:%Y%m%dT%H%M%S%f}"
    if folder.exists():
        raise FileExistsError(f"raw files are never overwritten: {folder}")
    folder.mkdir(parents=True)
    for one in series:
        params = {**one.filters, "sinceTimePeriod": one.since}
        response = session.get(URL.format(dataset=one.dataset), params=params, timeout=60)
        response.raise_for_status()
        (folder / f"{one.id}.json").write_text(response.text, encoding="utf-8")
    logger.info("Eurostat series %s written to %s", [s.id for s in series], folder)
    return folder


def write_landing(raw_dir: Path) -> Path:
    """Newest download into the landing file; empty before the first download."""
    folders = sorted(p for p in eurostat_dir(raw_dir).glob("*") if p.is_dir())
    frames = []
    if folders:
        for path in sorted(folders[-1].glob("*.json")):
            frames.append(parse(json.loads(path.read_text(encoding="utf-8")), path.stem))
    landing = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    landing = landing.astype({"series_id": "string", "value": "float64"})
    landing["date"] = pd.to_datetime(landing["date"])
    path = eurostat_dir(raw_dir) / "landing_eurostat.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    landing.to_parquet(path, index=False)
    return path
