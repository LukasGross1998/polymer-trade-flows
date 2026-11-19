"""dbt marts for shipping (PortWatch) and market data, built from the fixture raw layer.

The fixtures are described in tests/helpers.py (write_portwatch_raw, write_fred_csv).
"""

import pandas as pd
import pytest
from helpers import PipelineSetup

from ptf.core.warehouse import read_table


def table(setup: PipelineSetup, name: str) -> pd.DataFrame:
    return read_table(setup.settings, f"marts.{name}")


def test_latest_download_wins_per_day(warehouse_setup: PipelineSetup) -> None:
    transits = table(warehouse_setup, "mart_chokepoint_transits")
    suez = transits[
        (transits["chokepoint_id"] == "chokepoint1") & (transits["date"] == "2026-11-08")
    ]

    assert len(transits) == 18  # the revision replaces a row, it does not add one
    assert suez["n_total"].tolist() == [99]
    assert suez["chokepoint"].tolist() == ["Suez Canal"]


def test_only_configured_ports_with_their_short_names(warehouse_setup: PipelineSetup) -> None:
    activity = table(warehouse_setup, "mart_port_activity")
    ports = table(warehouse_setup, "dim_port")

    assert set(activity["port_id"]) == {"port24"}  # port999 is downloaded but not configured
    assert set(activity["port"]) == {"Jubail"}
    assert ports.loc[0, "role"] == "Saudi petrochemical port inside the Gulf"


def test_event_dates_from_epoch_milliseconds(warehouse_setup: PipelineSetup) -> None:
    events = table(warehouse_setup, "fct_disruption_events").set_index("event")

    assert str(events.loc["HORMUZ-26", "from_date"].date()) == "2026-03-01"
    assert pd.isna(events.loc["HORMUZ-26", "to_date"])  # still ongoing
    assert str(events.loc["BAVI-26", "to_date"].date()) == "2026-07-11"


def test_self_links_are_dropped(warehouse_setup: PipelineSetup) -> None:
    links = table(warehouse_setup, "fct_port_links")

    assert links["to_port_id"].tolist() == ["port1201"]


def test_market_series_long_table_with_metadata(warehouse_setup: PipelineSetup) -> None:
    market = table(warehouse_setup, "mart_market_series")
    brent = market[market["series_id"] == "DCOILBRENTEU"]

    assert len(brent) == 4  # the empty and the "." day of the FRED file are dropped
    assert set(market["series_id"]) == {
        "DCOILBRENTEU",
        "DHHNGSP",
        "PNGASEUUSDM",
        "GSCPI",
        "DCE_LLDPE",
        "EU_PPI_PLASTICS",  # Eurostat (spec 019)
    }
    assert brent["unit"].iloc[0] == "USD/bbl"
    dce = market[market["series_id"] == "DCE_LLDPE"].set_index("date")
    assert dce.loc[pd.Timestamp("2026-11-13"), "value"] == 8578.0  # closing price, CNY/t
    assert dce["group"].iloc[0] == "china_futures"


def test_brent_annual_averages(warehouse_setup: PipelineSetup) -> None:
    annual = table(warehouse_setup, "mart_brent_annual").set_index("year")

    assert annual.loc[2023, "brent_usd_per_bbl"] == pytest.approx(78.0)
    assert annual.loc[2024, "quoted_days"] == 2


def test_calendar_covers_the_data(warehouse_setup: PipelineSetup) -> None:
    calendar = table(warehouse_setup, "dim_date")

    assert calendar["date"].min() == pd.Timestamp("2019-01-01")
    assert calendar["iso_week"].max() == 52  # week 53 folded into 52


def test_marine_weather_with_names_and_forecast_flag(warehouse_setup: PipelineSetup) -> None:
    weather = table(warehouse_setup, "mart_marine_weather").set_index(["location_id", "date"])

    jubail = weather.loc[("port24", pd.Timestamp("2026-11-13"))]
    assert jubail["location"] == "Jubail"  # short name from config/shipping.yaml
    assert jubail["wind_gusts_kmh"] == 95.0
    assert bool(jubail["is_forecast"])  # downloaded on 8 Nov
    assert not bool(weather.loc[("port24", pd.Timestamp("2026-11-08")), "is_forecast"])
    assert (
        weather.loc[("chokepoint4", pd.Timestamp("2026-11-06")), "location"]
        == "Bab el-Mandeb Strait"
    )
