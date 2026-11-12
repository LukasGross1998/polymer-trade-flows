"""The Dash app without a browser: build it on fixture data and call the tab update functions."""

import json
from pathlib import Path

import pandas as pd
import pytest
from test_ingest_comtrade import FakeResponse, FakeSession, no_sleep

from ptf.app.__main__ import create_app
from ptf.app.data import load_app_data
from ptf.app.tabs import chokepoints, flows, markets, overview, ports
from ptf.clean.portwatch import clean_transits
from ptf.config import Settings
from ptf.ingest import portwatch

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Clean chokepoint tables from the 18-row fixture (Suez, Bab el-Mandeb, Cape) only."""
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", config_dir=REPO_ROOT / "config")
    features = json.loads((FIXTURES / "portwatch_daily_sample.json").read_text())["features"]
    session = FakeSession([FakeResponse(200, {"features": features})])
    portwatch.ingest_chokepoint_transits(settings.raw_dir, session=session, sleep=no_sleep)

    settings.clean_dir.mkdir(parents=True)
    clean_transits(settings.raw_dir).to_parquet(settings.clean_dir / "chokepoint_transits.parquet")
    pd.DataFrame(
        {
            "chokepoint_id": ["chokepoint1", "chokepoint4", "chokepoint7"],
            "chokepoint": ["Suez Canal", "Bab el-Mandeb Strait", "Cape of Good Hope"],
            "lat": [30.6, 12.6, -34.4],
            "lon": [32.4, 43.3, 18.5],
        }
    ).to_parquet(settings.clean_dir / "chokepoints.parquet")
    return settings


def add_market_and_port_data(settings: Settings) -> None:
    days = pd.date_range("2026-10-01", "2026-11-08")
    market = pd.concat(
        [
            pd.DataFrame({"date": days, "series_id": "DCOILBRENTEU", "value": 100.0}),
            pd.DataFrame({"date": days, "series_id": "DHHNGSP", "value": 3.0}),
            pd.DataFrame(
                {"date": [pd.Timestamp("2026-10-01")], "series_id": "PNGASEUUSDM", "value": [25.0]}
            ),
            pd.DataFrame(
                {"date": [pd.Timestamp("2026-10-31")], "series_id": "GSCPI", "value": [1.26]}
            ),
        ]
    ).assign(name="n", unit="u", frequency="f", group="g")
    market.to_parquet(settings.clean_dir / "market_series.parquet")

    activity = pd.DataFrame({"date": days, "port_id": "port24", "port": "Jubail"})
    for metric in ["portcalls", "portcalls_tanker", "portcalls_container", "import", "export"]:
        activity[metric] = 5
    activity.assign(fetched_at=pd.Timestamp("2026-11-12")).to_parquet(
        settings.clean_dir / "port_activity.parquet"
    )
    pd.DataFrame(
        {
            "port_id": ["port24"],
            "port": ["Jubail"],
            "country": ["Saudi Arabia"],
            "lat": [27.0],
            "lon": [49.7],
        }
    ).to_parquet(settings.clean_dir / "ports.parquet")


def test_chokepoint_tab_returns_all_outputs(settings: Settings) -> None:
    data = load_app_data(settings)

    map_fig, kpis, series_fig, diversion_fig = chokepoints.update(
        data, "chokepoint4", "container", "90d"
    )

    assert len(map_fig.data[0].lon) == 3  # one marker per chokepoint
    assert len(kpis) == 4
    assert [t.name for t in series_fig.data][-1] == "7-day average"
    assert len(diversion_fig.data) == 3


def test_app_builds_without_optional_data(settings: Settings) -> None:
    app = create_app(settings)

    layout_ids = {c.id for c in app.layout._traverse() if getattr(c, "id", None)}
    assert {"cp-select", "cp-map", "ov-kpis", "refresh"} <= layout_ids
    assert "mkt-oil" not in layout_ids  # no market data: the tab shows a hint instead


def test_all_tabs_with_market_and_port_data(settings: Settings) -> None:
    add_market_and_port_data(settings)
    data = load_app_data(settings)

    kpis, oil, gas, indexed_fig, gscpi = markets.update(data, "1y")
    assert kpis[0].children[1].children == "100.0"  # Brent tile
    assert len(oil.data) == 1  # WTI missing in the test data: only Brent is drawn

    port_outputs = ports.update(data, "port24", "export", "90d")
    assert len(port_outputs) == 4

    ov_kpis, *_ = overview.update(data)
    assert ov_kpis[0].children[1].children.endswith("of 3")  # disrupted chokepoints

    app = create_app(settings)
    layout_ids = {c.id for c in app.layout._traverse() if getattr(c, "id", None)}
    assert {"mkt-oil", "port-map"} <= layout_ids


def add_flow_data(settings: Settings) -> None:
    links = pd.DataFrame(
        [
            {
                "from_port_id": "jub",
                "from_port": "Jubail",
                "from_country": "Saudi Arabia",
                "from_lat": 27.0,
                "from_lon": 49.7,
                "to_port_id": "sgp",
                "to_port": "Singapore",
                "to_country": "Singapore",
                "to_lat": 1.3,
                "to_lon": 103.8,
                "transit_days": 14.6,
                "daily_capacity": 14652.0,
            }
        ]
    )
    links.to_parquet(settings.clean_dir / "port_links.parquet")
    days = pd.date_range("2026-09-01", "2026-11-06")
    trade = pd.DataFrame({"date": days, "iso3": "SAU", "country": "Saudi Arabia"})
    for flow in ("import", "export"):
        trade[flow] = 100.0
        for cargo in ["tanker", "dry_bulk", "container", "general_cargo", "roro"]:
            trade[f"{flow}_{cargo}"] = 20.0
    trade.assign(fetched_at=pd.Timestamp("2026-11-12")).to_parquet(
        settings.clean_dir / "country_trade.parquet"
    )


def test_flows_tab(settings: Settings) -> None:
    add_flow_data(settings)
    data = load_app_data(settings)

    network_fig, table = flows.update_network(data, flows.ALL_PORTS, "outbound", ["intl"])
    mix_fig, ranking_fig = flows.update_trade(data, "SAU", "export", "tanker", "1y")

    port_markers = network_fig.data[-1]
    assert list(port_markers.customdata) == ["jub", "sgp"]  # clickable ports
    assert [t.name for t in mix_fig.data] == [
        "Tankers",
        "Dry bulk",
        "Containers",
        "General cargo",
        "RoRo",
    ]
    assert list(ranking_fig.data[0].y) == ["Saudi Arabia"]

    app = create_app(settings)
    layout_ids = {c.id for c in app.layout._traverse() if getattr(c, "id", None)}
    assert {"flow-map", "flow-mix", "flow-ranking"} <= layout_ids
