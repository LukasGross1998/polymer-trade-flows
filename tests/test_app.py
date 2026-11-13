"""The Dash app without a browser: load the warehouse and call the tab update functions."""

import dataclasses

import pandas as pd
import pytest
from helpers import PipelineSetup

from ptf import warehouse
from ptf.app.__main__ import create_app
from ptf.app.data import AppData, load_app_data
from ptf.app.tabs import chokepoints, flows, markets, overview, ports
from ptf.monitor.config import load_monitor_config


def layout_ids(setup: PipelineSetup) -> set[str]:
    app = create_app(setup.settings)
    return {c.id for c in app.layout._traverse() if getattr(c, "id", None)}


@pytest.fixture
def data(warehouse_setup: PipelineSetup) -> AppData:
    return load_app_data(warehouse_setup.settings)


@pytest.fixture
def shipping_only(pipeline_setup: PipelineSetup) -> PipelineSetup:
    """A warehouse with the shipping marts only (no `pipeline market` run yet)."""
    settings = pipeline_setup.settings
    config = load_monitor_config(settings.config_dir / "monitor.yaml")
    warehouse.write_port_reference(config, settings.raw_dir)
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


def test_market_port_and_overview_tabs(data: AppData) -> None:
    kpis, oil, *_ = markets.update(data, "5y")
    assert kpis[0].children[1].children == "78.0"  # latest Brent in the FRED fixture
    assert len(oil.data) == 1  # WTI missing in the fixtures: only Brent is drawn

    assert len(ports.update(data, "port24", "export", "90d")) == 4

    ov_kpis, *_ = overview.update(data)
    assert ov_kpis[0].children[1].children.endswith("of 3")  # disrupted chokepoints


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

    assert {"cp-map", "port-map", "flow-map", "mkt-oil", "ov-kpis"} <= ids
    assert "flow-mix" not in ids  # country trade switched off: hint instead of charts


def test_app_without_market_data_shows_hints(shipping_only: PipelineSetup) -> None:
    ids = layout_ids(shipping_only)

    assert {"cp-select", "cp-map", "port-map", "ov-kpis"} <= ids
    assert "mkt-oil" not in ids  # no market marts yet: the tab shows a hint
