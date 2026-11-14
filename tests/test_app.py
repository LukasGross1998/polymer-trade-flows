"""The Dash app without a browser: load the warehouse and call the tab update functions."""

import dataclasses
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest
from flask import Flask
from helpers import REPO_ROOT, PipelineSetup, write_synthetic_distances

from ptf.app import weather_card
from ptf.app.__main__ import create_app
from ptf.app.data import AppData, load_app_data
from ptf.app.tabs import (
    chokepoints,
    classes,
    flows,
    landed_cost,
    planner,
    ports,
    prices,
    situation,
    sourcing,
)
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

    assert len(map_fig.data[0].lon) == 1  # dark dot behind the selected chokepoint
    assert len(map_fig.data[1].lon) == 3  # one marker per chokepoint
    assert map_fig.layout.map.layers == ()  # nautical chart layer off by default
    assert len(kpis) == 4
    assert [t.name for t in series_fig.data][-1] == "7-day average"
    assert len(diversion_fig.data) == 3


def test_prices_port_and_situation_tabs(data: AppData) -> None:
    kpis, drivers, dce_fig, quote, oil, *_ = prices.update(data, "5y", "USD")
    # Fixture quote: trading day 16 Nov, newer than the last close (13 Nov) -> shown.
    assert quote.startswith(
        "Latest quote: 8,547 CNY/t (bid 8,547 / ask 8,551), last trade 23:00:00"
    )
    assert "fetched Sat 14 Nov 17:05" in quote  # 16:05 UTC = 17:05 CET
    # DCE price in the fixtures, but no CNY rate (DEXCHUS): the chart explains instead of failing.
    assert "not available" in dce_fig.layout.annotations[0].text
    assert kpis[0].children[1].children == "78.0"  # latest Brent in the FRED fixture
    assert len(oil.data) == 1  # WTI missing in the fixtures: only Brent is drawn
    assert drivers.layout.title.text.startswith("Feedstock vs. resin prices in USD")

    assert len(ports.update(data, "port24", "export", "90d")) == 4

    lights, *_ = situation.update(data)
    assert [card.children[0].children[0].children[0] for card in lights] == [
        "Price",
        "Supply",
        "Logistics",
        "Polyethylene",
    ]
    links = [card.children[-1].children for card in lights]
    assert [(b.children, b.id["tab"]) for b in links] == [
        ("Review drivers →", "prices"),
        ("Check routes →", "sourcing"),
        ("View delays →", "planner"),
        ("See PE prices →", "prices"),
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

    kpis, bars, table = landed_cost.update(data, "open", "baci")
    # Fixture: USA -> Germany 2,000 t for 2.5 m USD = 1,250 USD/t; US duty 0 % (TARIC); no
    # sourced freight rate (spec 015): price + duty; no EUR rate in the fixtures: 1 USD = 1 EUR.
    assert kpis[0].children[0].children == "Lowest cost origin, price + duty, excl. freight"
    assert kpis[0].children[1].children == "1,250 EUR/t"
    assert [t.name for t in bars.data] == ["Price (FOB)", "EU duty"]
    assert table.children[1].children[4].children == "n/a"  # freight column

    closed, *_ = landed_cost.update(data, "closed", "baci")
    assert closed[0].children[1].children == "1,250 EUR/t"  # longer route, no freight cost
    assert closed[2].children[2].children == "n/a – no sourced freight rate"


def test_world_trade_by_class_tab(data: AppData) -> None:
    kpis, shares, treemap, index = classes.update(data)

    # Fixture 2023: 12,499 t in total, of which 9,999 t crude oil (80 %) and 2,500 t PE.
    assert kpis[1].children[1].children == "80 % of tonnes"
    assert "Polyethylene" in list(treemap.data[0].labels)
    assert [t.name for t in shares.data] == ["Share of tonnes", "Share of value"]


def test_vessel_classes_at_a_chokepoint(data: AppData) -> None:
    figure = chokepoints.classes_figure(data, "chokepoint4")
    table = chokepoints.class_table(data, "chokepoint4")

    assert [t.name for t in figure.data][:2] == ["Container", "Tanker"]
    assert "By carrying capacity" in table.children[1].children


def test_grade_filter_in_sourcing_and_landed_cost(warehouse_setup: PipelineSetup) -> None:
    raw, regions = warehouse_setup.settings.raw_dir, warehouse_setup.regions
    write_synthetic_distances(raw, regions)
    data = load_app_data(warehouse_setup.settings)

    assert [o["value"] for o in data.grade_options()][:2] == ["all", "390110"]
    kpis, *_ = sourcing.update(data, "390120")
    assert kpis[0].children[1].children == "0.0 Mt"  # 1,000 t HDPE from the USA in 2023
    # HDPE only: 1.2 m USD for 1,000 t = 1,200 USD/t, US duty 0 %, freight not sourced.
    landed, *_ = landed_cost.update(data, "open", "baci", "390120")
    assert landed[0].children[1].children == "1,200 EUR/t"


def test_weather_card_and_seamark_layer(data: AppData) -> None:
    waves, gusts, note = weather_card.update(data, "port24", today=pd.Timestamp("2026-11-12"))

    # Fixture: Jubail gusts 95 km/h and waves 4.5 m on 13 Nov -> storm (gusts >= 88.9 km/h).
    assert note.children == "▲ Storm forecast on 13 Nov: waves 4.5 m, gusts 95 km/h"
    assert [t.name for t in waves.data] == ["observed", "forecast"]
    assert weather_card.update(data, "chokepoint4", today=pd.Timestamp("2026-11-12"))[
        2
    ].children == ("● No gale or storm in the forecast")

    map_fig, *_ = chokepoints.update(data, "chokepoint4", "container", "90d", seamarks=True)
    assert "openseamap" in map_fig.layout.map.layers[0].source[0]


def test_order_planner_tab(warehouse_setup: PipelineSetup) -> None:
    raw, regions = warehouse_setup.settings.raw_dir, warehouse_setup.regions
    write_synthetic_distances(raw, regions)
    data = load_app_data(warehouse_setup.settings)
    order = pd.Timestamp("2026-11-14")

    kpis, scatter, table = planner.update(data, "2027-01-31", 500, order_date=order)
    # Fixture: only the USA ship to Europe. UNCTAD port days USA 1.08 + Netherlands 0.80;
    # 5,000 nm / (16.3 kn x 24) = 12.8 sea days -> 14.7, rounded 15 days -> 29 Nov.
    # No sourced freight rate: no recommendation (spec 015).
    assert kpis[0].children[1].children == "none"
    assert kpis[0].children[2].children == "sea freight has no sourced rate"
    assert kpis[1].children[1].children == "15 days"
    assert kpis[1].children[2].children == "USA, arrives 29 Nov 2026"
    assert scatter.data[0].x[0] == pd.Timestamp("2026-11-29")

    late, *_ = planner.update(data, "2026-11-20", 500, order_date=order)
    assert late[2].children[1].children == "0 of 1"


def test_dce_price_converted_to_usd_and_eur(data: AppData) -> None:
    rates = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-11-12", "2026-11-12"]),
            "series_id": ["DEXCHUS", "DEXUSEU"],
            "value": [7.20, 1.10],
        }
    )
    market = pd.concat([data.market, rates], ignore_index=True)

    usd = prices.dce_in_currency(market, "USD").set_index("date")["value"]
    eur = prices.dce_in_currency(market, "EUR").set_index("date")["value"]

    assert usd[pd.Timestamp("2026-11-13")] == pytest.approx(8578 / 7.20)  # 1,191.39 USD/t
    assert eur[pd.Timestamp("2026-11-13")] == pytest.approx(8578 / 7.20 / 1.10)
    kpis = prices.kpi_values(market, "USD")
    assert kpis[-1]["label"] == "LLDPE Dalian, USD/t" and kpis[-1]["value"] == "1,191"


def test_navigation_and_freshness(data: AppData) -> None:
    from dash import no_update

    from ptf.app.__main__ import freshness, navigate

    assert navigate("planner") == ("buying", "planner", no_update)
    assert navigate("chokepoints") == ("markets", no_update, "chokepoints")
    assert "chokepoints to 08 Nov" in freshness(data)
    assert freshness(data).startswith("Last updated: ")


def test_situation_europe_filter(warehouse_setup: PipelineSetup) -> None:
    raw, regions = warehouse_setup.settings.raw_dir, warehouse_setup.regions
    write_synthetic_distances(raw, regions)
    data = load_app_data(warehouse_setup.settings)
    assert data.relevance is not None
    # Fixture: Europe imports only from North America (no chokepoint) -> Dover only.
    assert data.relevance.chokepoints == {"chokepoint9"}
    assert "port24" not in data.relevance.ports  # Jubail: no Middle East imports here

    today = pd.Timestamp("2026-11-12")
    europe = situation.change_items(data, situation.EUROPE, today)
    everything = situation.change_items(data, situation.ALL, today)
    text = lambda items: " ".join(str(i) for i in items)  # noqa: E731
    assert "Jubail" not in text(europe)  # storm forecast at Jubail filtered out for Europe
    assert "Jubail" in text(everything)


def test_weather_text_leaves_out_missing_parts() -> None:
    assert situation.weather_text(1.4, 68.8) == "waves 1.4 m, gusts 69 km/h"
    assert situation.weather_text(float("nan"), 62.6) == "gusts 63 km/h"  # land point
