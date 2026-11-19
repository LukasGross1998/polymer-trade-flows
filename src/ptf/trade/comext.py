"""Monthly EU imports of polyethylene from Eurostat Comext (spec 019).

Dataset DS-045409 ("EU trade since 1988 by HS2-4-6 and CN8"), reporter EU27_2020, flow
import, all partners, per PE grade (HS6), value in EUR and quantity in 100 kg. Import values
are CIF at the EU border (Eurostat metadata ext_go_agg_esms): they include sea freight and
insurance to the border. Free reuse with attribution (Eurostat copyright notice, Decision
2011/833/EU); no key.

Raw layer: the JSON answers of each download in their own folder, never overwritten; the
newest download is parsed into `comext/landing_eu_imports.parquet` for dbt.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from ptf.core import jsonstat

logger = logging.getLogger(__name__)

URL = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
INDICATORS = {"VALUE_IN_EUROS": "value_eur", "QUANTITY_IN_100KG": "qty_100kg"}
COLUMNS = ["month", "partner_iso2", "hs6", "value_eur", "qty_100kg"]


def comext_dir(raw_dir: Path) -> Path:
    return raw_dir / "comext"


def query(hs6: str, since: str) -> dict[str, str | list[str]]:
    return {
        "freq": "M",
        "reporter": "EU27_2020",
        "product": hs6,
        "flow": "1",
        "indicators": list(INDICATORS),
        "sinceTimePeriod": since,
    }


def parse(answer: dict[str, object]) -> pd.DataFrame:
    """Rows of one JSON-stat answer: month, partner_iso2, hs6, value_eur, qty_100kg."""
    cells = jsonstat.rows(answer) if "value" in answer else []
    frame = pd.DataFrame(cells)
    if frame.empty:
        return pd.DataFrame(columns=COLUMNS)
    wide = frame.pivot_table(
        index=["time", "partner", "product"], columns="indicators", values="value", aggfunc="sum"
    ).reset_index()
    wide = wide.rename(columns={"time": "month", "partner": "partner_iso2", "product": "hs6"})
    wide = wide.rename(columns=INDICATORS)
    for column in INDICATORS.values():
        if column not in wide.columns:
            wide[column] = float("nan")
    return wide[COLUMNS]


def ingest_comext(
    raw_dir: Path,
    hs6_codes: list[str],
    since: str,
    session: requests.Session | None = None,
    today: datetime | None = None,
) -> Path:
    """One answer per grade into a new raw folder."""
    now = today or datetime.now(UTC)
    session = session or requests.Session()
    folder = comext_dir(raw_dir) / f"{now:%Y%m%dT%H%M%S%f}"
    if folder.exists():
        raise FileExistsError(f"raw files are never overwritten: {folder}")
    folder.mkdir(parents=True)
    for hs6 in hs6_codes:
        response = session.get(URL, params=query(hs6, since), timeout=120)
        response.raise_for_status()
        (folder / f"{hs6}.json").write_text(response.text, encoding="utf-8")
    logger.info("Comext imports for %s grades written to %s", len(hs6_codes), folder)
    return folder


def write_landing(raw_dir: Path, eu_members_iso2: list[str]) -> Path:
    """Parse the newest download into `landing_eu_imports.parquet`, without intra-EU partners;
    an empty file before the first download, so dbt always builds."""
    folders = sorted(p for p in comext_dir(raw_dir).glob("*") if p.is_dir())
    frames = []
    if folders:
        for path in sorted(folders[-1].glob("*.json")):
            frames.append(parse(json.loads(path.read_text(encoding="utf-8"))))
    landing = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    landing = landing[~landing["partner_iso2"].isin(eu_members_iso2)]
    landing = landing.astype({"month": "string", "partner_iso2": "string", "hs6": "string"}).astype(
        {"value_eur": "float64", "qty_100kg": "float64"}
    )
    path = comext_dir(raw_dir) / "landing_eu_imports.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    landing.to_parquet(path, index=False)
    return path
