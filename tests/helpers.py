"""Shared test helpers: paths, fake HTTP sessions and builders for small raw layers.

Test modules import from here; pytest fixtures live in conftest.py.
"""

import json
import shutil
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from ptf.config import Settings
from ptf.pipeline_config import PipelineConfig
from ptf.regions import RegionConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class PipelineSetup:
    settings: Settings
    regions: RegionConfig
    config: PipelineConfig


def write_raw_layer(raw_dir: Path) -> None:
    """Germany's real 2023 records plus one made-up US export report to Germany."""
    deu = pd.DataFrame(json.loads((FIXTURES / "comtrade_deu_2023.json").read_text())["data"])
    usa = deu[(deu["flowCode"] == "M") & (deu["partnerCode"] == 842)].copy()
    usa = usa.assign(reporterCode=842, partnerCode=276, flowCode="X")
    usa["netWgt"] = usa["netWgt"] * 0.9  # the US reports 10 % less than Germany receives

    (raw_dir / "comtrade").mkdir(parents=True)
    deu.to_parquet(raw_dir / "comtrade" / "DEU_2023.parquet")
    usa.to_parquet(raw_dir / "comtrade" / "USA_2023.parquet")

    areas = json.loads((FIXTURES / "partner_areas.json").read_text())["results"]
    (raw_dir / "comtrade_reference").mkdir()
    pd.DataFrame(areas).to_parquet(raw_dir / "comtrade_reference" / "partnerAreas.parquet")
    reporters = json.loads((FIXTURES / "reporters.json").read_text())["results"]
    pd.DataFrame(reporters).to_parquet(raw_dir / "comtrade_reference" / "Reporters.parquet")

    write_baci_zip(raw_dir / "baci" / "BACI_HS17_V202601.zip")

    brent_dir = raw_dir / "fred" / "DCOILBRENTEU"
    brent_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "brent_sample.csv", brent_dir / "20260101T000000000000.csv")


def write_synthetic_distances(raw_dir: Path, regions: RegionConfig) -> None:
    """5,000 nm between all regions: keeps model tests fast and independent of searoute."""
    rows = [
        {
            "origin_region": o,
            "dest_region": d,
            "origin_port": regions.regions[o].port.name,
            "dest_port": regions.regions[d].port.name,
            "distance_nm": 0.0 if o == d else 5000.0,
        }
        for o in regions.regions
        for d in regions.regions
    ]
    (raw_dir / "distances").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(raw_dir / "distances" / "sea_distances_base.parquet")


BACI_COUNTRIES = (
    "country_code,country_name,country_iso2,country_iso3\n"
    "276,Germany,DE,DEU\n"
    "842,USA,US,USA\n"
    "156,China,CN,CHN\n"
    "490,Other Asia nes,,S19\n"
)
# 2023: USA exports HDPE and LDPE to Germany, one flow without quantity, and crude oil (not PE).
BACI_2023 = (
    "t,i,j,k,v,q\n"
    "2023,842,276,390120,1200.0,1000.0\n"
    "2023,842,276,390110,1300.0,1000.0\n"
    "2023,842,156,390120,600.0,           NA\n"
    "2023,490,156,390110,650.0,500.0\n"
    "2023,842,276,270900,9999.0,9999.0\n"
)


def write_baci_zip(path: Path) -> None:
    """A tiny BACI-like zip: country codes and one year of flows (values in thousand USD)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("country_codes_V202601.csv", BACI_COUNTRIES)
        archive.writestr("BACI_HS17_Y2023_V202601.csv", BACI_2023)


# --- fake HTTP -----------------------------------------------------------------------------


class FakeResponse:
    """A canned `requests` response: status code, JSON payload, optional raw bytes."""

    def __init__(
        self, status_code: int, payload: dict[str, Any] | None = None, content: bytes = b""
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = {"Content-Length": str(len(content))}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start : start + chunk_size]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        pass


class FakeSession:
    """Returns the queued responses in order and records every request."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, "params": params})
        return self.responses.pop(0)


def no_sleep(seconds: float) -> None:
    pass


def arcgis_page(features: list[dict[str, Any]], more: bool) -> FakeResponse:
    """One page of an ArcGIS query result; `more` sets exceededTransferLimit."""
    payload: dict[str, Any] = {"features": features}
    if more:
        payload["exceededTransferLimit"] = True
    return FakeResponse(200, payload)
