"""The Dash app without a browser: load the warehouse and call the tab update functions."""

import dataclasses
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest
from flask import Flask
from helpers import REPO_ROOT, PipelineSetup, write_synthetic_distances

from ptf.app.__main__ import create_app
from ptf.app.data import AppData, load_app_data
from ptf.app.tabs import chokepoints, flows, landed_cost, ports, prices, situation, sourcing
from ptf.core import warehouse
from ptf.core.settings import Settings, get_settings
from ptf.shipping.config import load_monitor_config
from ptf.shipping.reference import write_port_reference


def layout_ids(setup: PipelineSetup) -> set[str]:
    app = create_app(setup.settings)
    return {c.id for c in app.layout._traverse() if getattr(c, "id", None)}


@pytest.fixture
def data(warehouse_setup: PipelineSetup) -> AppData:
    return load_app_data(warehouse_setup.settings)


@pytest.fixture
def shipping_only(pipeline_setup: PipelineSetup) -> PipelineSetup:
    """A warehouse with the shipping marts only (no `ptf market` run yet)."""
    settings = pipeline_setup.settings
    config = load_monitor_config(settings.config_dir / "shipping.yaml")
    write_port_reference(config, settings.raw_dir)
    warehouse.run_dbt(settings, ["build", "--select", "tag:shipping"])
    return pipeline_setup


def test_app_data_comes_from_the_warehouse(data: AppData) -> None:
    assert len(data.transits) == 18
    assert data.port_activity is not None
    assert set(data.port_activity["port"]) == {"Jubail"}
    assert data.country_trade is None  # optional model is disabled


def test_chokepoint_tab_returns_all_outputs(data: AppData) -> None:
    map_fig, kpis, series_fig, diversion_fig = chokepoints.update(
        data, "chokepoint4", "container", "90d"
    )

    assert len(map_fig.data[0].lon) == 3  # one marker per chokepoint
    assert len(kpis) == 4
    assert [t.name for t in series_fig.data][-1] == "7-day average"
    assert len(diversion_fig.data) == 3


def test_prices_port_and_situation_tabs(data: AppData) -> None:
    kpis, drivers, oil, *_ = prices.update(data, "5y", "USD")
    assert kpis[0].children[1].children == "78.0"  # latest Brent in the FRED fixture
    assert len(oil.data) == 1  # WTI missing in the fixtures: only Brent is drawn
    assert drivers.layout.title.text.startswith("Feedstock vs. resin prices in USD")

    assert len(ports.update(data, "port24", "export", "90d")) == 4

    lights, *_ = situation.update(data)
    assert [card.children[0].children[0].children for card in lights] == [
        "Price",
        "Supply",
        "Logistics",
    ]


def test_sourcing_tab_with_routes(warehouse_setup: PipelineSetup) -> None:
    write_synthetic_distances(warehouse_setup.settings.raw_dir, warehouse_setup.regions)
    data = load_app_data(warehouse_setup.settings)

    assert data.sourcing is not None
    kpis, sankey, treemap = sourcing.update(data)
    # The BACI fixture: Germany imports 2,000 t from the USA in 2023, nothing from Europe.
    assert kpis[0].children[1].children == "0.0 Mt"
    assert data.sourcing.extra_t == pytest.approx(2000)
    assert data.sourcing.exposure_pct == 0.0  # North America -> Europe passes no chokepoint
    assert "Europe" in sankey.data[0].node.label
    assert "United States" in " ".join(treemap.data[0].labels) or "USA" in treemap.data[0].ids


def test_flows_tab_network_and_injected_country_trade(data: AppData) -> None:
    network_fig, _table = flows.update_network(data, flows.ALL_PORTS, "outbound", ["long"])
    assert sorted(network_fig.data[-1].customdata) == ["port1201", "port24"]  # clickable

    days = pd.date_range("2026-09-01", "2026-11-06")
    trade = pd.DataFrame({"date": days, "iso3": "SAU", "country": "Saudi Arabia"})
    for flow in ("import", "export"):
        trade[flow] = 100.0
        for cargo in ["tanker", "dry_bulk", "container", "general_cargo", "roro"]:
            trade[f"{flow}_{cargo}"] = 20.0
    with_trade = dataclasses.replace(data, country_trade=trade)

    mix_fig, ranking_fig = flows.update_trade(with_trade, "SAU", "export", "tanker", "1y")
    names = [t.name for t in mix_fig.data]
    assert names == ["Tankers", "Dry bulk", "Containers", "General cargo", "RoRo"]
    assert list(ranking_fig.data[0].y) == ["Saudi Arabia"]


def test_full_app_layout(warehouse_setup: PipelineSetup) -> None:
    ids = layout_ids(warehouse_setup)

    assert {"cp-map", "port-map", "flow-map", "mkt-oil", "mkt-drivers", "sit-lights"} <= ids
    assert "flow-mix" not in ids  # country trade switched off: hint instead of charts


def test_app_without_market_data_shows_hints(shipping_only: PipelineSetup) -> None:
    ids = layout_ids(shipping_only)

    assert {"cp-select", "cp-map", "port-map", "sit-lights"} <= ids
    assert "mkt-oil" not in ids  # no market marts yet: the tab shows a hint


def test_app_without_warehouse_shows_start_page(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", config_dir=REPO_ROOT / "config")
    assert not warehouse.table_exists(settings, "marts.mart_chokepoint_transits")

    app = create_app(settings)
    assert app.layout.id == "no-data"  # a hint instead of the tabs, no crash


def test_wsgi_module_exposes_the_flask_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    sys.modules.pop("ptf.app.wsgi", None)

    wsgi = importlib.import_module("ptf.app.wsgi")

    assert isinstance(wsgi.server, Flask)
    get_settings.cache_clear()


def test_landed_cost_tab_open_and_closed(warehouse_setup: PipelineSetup) -> None:
    raw, regions = warehouse_setup.settings.raw_dir, warehouse_setup.regions
    write_synthetic_distances(raw, regions)
    write_synthetic_distances(raw, regions, "red_sea_closed", distance_nm=10000.0)
    data = load_app_data(warehouse_setup.settings)

    kpis, bars, table = landed_cost.update(data, "open", 1.0, "baci")
    # Fixture: USA -> Germany 2,000 t for 2.5 m USD = 1,250 USD/t; freight 40 + 7 x 5 = 75;
    # US duty 0 %; no EUR rate in the fixtures, so 1 USD = 1 EUR.
    assert kpis[0].children[1].children == "1,325 EUR/t"
    assert [t.name for t in bars.data] == ["Price (FOB)", "Sea freight", "EU duty"]

    closed, *_ = landed_cost.update(data, "closed", 2.0, "baci")
    assert closed[0].children[1].children == "1,470 EUR/t"  # freight (40 + 70) x 2 = 220
