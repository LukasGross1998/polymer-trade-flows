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

from ptf.core import warehouse
from ptf.core.regions import RegionConfig
from ptf.core.settings import Settings
from ptf.markets.config import load_market_config
from ptf.markets.reference import write_market_reference
from ptf.shipping.config import load_monitor_config
from ptf.shipping.reference import write_port_reference
from ptf.trade.baci import baci_zip_path, write_landing
from ptf.trade.config import load_trade_config
from ptf.trade.duties import write_duty_landing
from ptf.trade.reference import write_reference_tables

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class PipelineSetup:
    settings: Settings
    regions: RegionConfig


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
    write_fred_csv(raw_dir, "DHHNGSP", [("2026-09-01", 2.0), ("2026-09-15", 4.0)])
    write_fred_csv(raw_dir, "PNGASEUUSDM", [("2026-09-01", 25.0)])

    write_portwatch_raw(raw_dir)


def write_fred_csv(raw_dir: Path, series_id: str, rows: list[tuple[str, float]]) -> None:
    """A FRED download as served: header "observation_date,<id>", one row per day."""
    folder = raw_dir / "fred" / series_id
    folder.mkdir(parents=True, exist_ok=True)
    lines = [f"observation_date,{series_id}", *[f"{d},{v}" for d, v in rows]]
    (folder / "20260101T000000000000.csv").write_text("\n".join(lines) + "\n")


def write_portwatch_raw(raw_dir: Path) -> None:
    """PortWatch downloads as written by ptf.shipping.portwatch (one Parquet per download).

    Chokepoints: the real 18-row sample (Suez, Bab el-Mandeb, Cape, 2026-11-03..08) plus a
    later download that revises Suez on 2026-11-08 to 99 transits. Ports: the configured
    port24 (Jubail) and port999, which is downloaded but not configured. Events: one open
    and one closed event. Links: one real link and one self-link that must be dropped.
    """
    portwatch = raw_dir / "portwatch"
    first = pd.DataFrame(
        [
            f["attributes"]
            for f in json.loads((FIXTURES / "portwatch_daily_sample.json").read_text())["features"]
        ]
    ).assign(fetched_at=pd.Timestamp("2026-11-10", tz="UTC"))
    revised = first[(first["portid"] == "chokepoint1") & (first["date"] == "2026-11-08")].assign(
        n_total=99, fetched_at=pd.Timestamp("2026-11-12", tz="UTC")
    )
    (portwatch / "chokepoints_daily").mkdir(parents=True)
    first.to_parquet(portwatch / "chokepoints_daily" / "20261110T000000000000.parquet")
    revised.to_parquet(portwatch / "chokepoints_daily" / "20261112T000000000000.parquet")
    pd.DataFrame(
        {
            "portid": ["chokepoint1", "chokepoint4", "chokepoint7"],
            "portname": ["Suez Canal", "Bab el-Mandeb Strait", "Cape of Good Hope"],
            "lat": [30.6, 12.6, -34.4],
            "lon": [32.4, 43.3, 18.5],
        }
    ).to_parquet(portwatch / "chokepoints.parquet")

    days = [f"2026-11-{d:02d}" for d in range(1, 7)]
    ports_daily = pd.DataFrame(
        [
            {
                "date": d,
                "portid": p,
                "portname": p,
                "portcalls": 5,
                "portcalls_tanker": 2,
                "portcalls_container": 1,
                "import": 100,
                "export": 200,
            }
            for d in days
            for p in ("port24", "port999")
        ]
    ).assign(fetched_at=pd.Timestamp("2026-11-10", tz="UTC"))
    (portwatch / "ports_daily").mkdir()
    ports_daily.to_parquet(portwatch / "ports_daily" / "20261110T000000000000.parquet")
    pd.DataFrame(
        {
            "portid": ["port24", "port999"],
            "portname": ["Jubail", "Elsewhere"],
            "country": ["Saudi Arabia", "Nowhere"],
            "lat": [27.06, 0.0],
            "lon": [49.66, 0.0],
        }
    ).to_parquet(portwatch / "ports.parquet")

    events = pd.DataFrame(
        {
            "eventid": [1, 2],
            "eventtype": ["OT", "TC"],
            "eventname": ["HORMUZ-26", "BAVI-26"],
            "alertlevel": ["RED", "RED"],
            "country": [None, "China"],
            "fromdate": [1772323200000, 1782864000000],  # 2026-03-01, 2026-07-01
            "todate": [float("nan"), 1783792800000.0],  # open, 2026-07-11
            "lat": [26.3, 20.0],
            "long": [56.9, 120.0],
            "affectedports": ["chokepoint6", ""],
            "n_affectedports": [1, 37],
            "htmldescription": ["Trade Disruptions in the Strait of Hormuz", "Cyclone"],
        }
    ).assign(fetched_at=pd.Timestamp("2026-11-10", tz="UTC"))
    (portwatch / "events").mkdir()
    events.to_parquet(portwatch / "events" / "20261110T000000000000.parquet")

    def link(src: str, dst: str, capacity: float) -> dict[str, Any]:
        return {
            "from_portid": src,
            "from_portname": src,
            "from_country": "Saudi Arabia",
            "from_lat": 27.0,
            "from_lon": 49.7,
            "to_portid": dst,
            "to_portname": dst,
            "to_country": "Singapore",
            "to_lat": 1.3,
            "to_lon": 103.8,
            "average_transit_days": 14.6,
            "daily_capacity_at_risk": capacity,
        }

    links = pd.DataFrame([link("port24", "port1201", 14652.0), link("port24", "port24", 999.0)])
    (portwatch / "port_links").mkdir()
    links.assign(fetched_at=pd.Timestamp("2026-11-10", tz="UTC")).to_parquet(
        portwatch / "port_links" / "20261110T000000000000.parquet"
    )

    # Marine weather (spec 009): Bab el-Mandeb calm, Jubail with a storm forecast on 13 Nov.
    days = pd.to_datetime([f"2026-11-{d:02d}" for d in range(6, 15)])
    weather = pd.concat(
        [
            pd.DataFrame(
                {
                    "location_id": "chokepoint4",
                    "location_type": "chokepoint",
                    "date": days,
                    "wave_height_m": 1.0,
                    "wind_gusts_kmh": 40.0,
                    "wind_speed_kmh": 20.0,
                }
            ),
            pd.DataFrame(
                {
                    "location_id": "port24",
                    "location_type": "port",
                    "date": days,
                    "wave_height_m": [0.5] * 7 + [4.5, 1.0],
                    "wind_gusts_kmh": [30.0] * 7 + [95.0, 30.0],
                    "wind_speed_kmh": 15.0,
                }
            ),
        ]
    ).assign(fetched_at=pd.Timestamp("2026-11-08", tz="UTC"))
    (raw_dir / "weather").mkdir()
    weather.to_parquet(raw_dir / "weather" / "20261108T000000000000.parquet")


def build_warehouse(setup: "PipelineSetup") -> None:
    """Landing files, reference tables and a full `dbt build`, offline (no downloads)."""
    settings, raw = setup.settings, setup.settings.raw_dir
    baci_config = load_trade_config(settings.config_dir / "trade.yaml").baci
    write_landing(
        baci_zip_path(raw, baci_config.hs_revision, baci_config.version),
        baci_config.years,
        baci_config.hs_prefix,
        raw,
    )
    # WITS duties: the saved real answer for LDPE (6.5 % in 2022) as one download.
    wits = raw / "wits" / "20261101T000000000000"
    wits.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "wits_eu_390110_2022.xml", wits / "390110_2022.xml")
    write_duty_landing(raw)
    write_reference_tables(setup.regions, raw)
    write_port_reference(load_monitor_config(settings.config_dir / "shipping.yaml"), raw)
    write_market_reference(load_market_config(settings.config_dir / "markets.yaml"), raw)
    gscpi = raw / "gscpi"
    gscpi.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"date": pd.to_datetime(["2026-09-30", "2026-10-31"]), "value": [1.36, 1.26]}
    ).to_parquet(gscpi / "landing_gscpi.parquet")
    warehouse.run_dbt(settings, ["build"])


def write_synthetic_distances(
    raw_dir: Path, regions: RegionConfig, variant: str = "base", distance_nm: float = 5000.0
) -> None:
    """5,000 nm between all regions: keeps model tests fast and independent of searoute.

    Routes from the Middle East pass Hormuz and Suez, all others no passage.
    """
    rows = [
        {
            "origin_region": o,
            "dest_region": d,
            "origin_port": regions.regions[o].port.name,
            "dest_port": regions.regions[d].port.name,
            "distance_nm": 0.0 if o == d else distance_nm,
            "passages": ["ormuz", "suez"] if o == "MDE" and d != "MDE" else [],
        }
        for o in regions.regions
        for d in regions.regions
    ]
    (raw_dir / "distances").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(raw_dir / "distances" / f"sea_distances_{variant}.parquet")


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


BACI_PRODUCTS = (
    "code,description\n"
    '390110,"Ethylene polymers: polyethylene with specific gravity < 0.94"\n'
    '390120,"Ethylene polymers: polyethylene with specific gravity >= 0.94"\n'
    '270900,"Petroleum oils, crude"\n'
)


def write_baci_zip(path: Path) -> None:
    """A tiny BACI-like zip: code lists and one year of flows (values in thousand USD)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("country_codes_V202601.csv", BACI_COUNTRIES)
        archive.writestr("product_codes_HS17_V202601.csv", BACI_PRODUCTS)
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
