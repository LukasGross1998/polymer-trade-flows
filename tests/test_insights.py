"""Buyer view (spec 006): chokepoint exposure and traffic lights with hand-checkable numbers."""

from pathlib import Path

import pandas as pd
import pytest

from ptf.insights import exposure, signals
from ptf.insights.config import load_sourcing_config

CONFIG = load_sourcing_config(Path(__file__).resolve().parents[1] / "config" / "sourcing.yaml")

CHOKEPOINTS = pd.DataFrame(
    {
        "chokepoint_id": ["chokepoint1", "chokepoint4", "chokepoint6", "chokepoint8"],
        "chokepoint": [
            "Suez Canal",
            "Bab el-Mandeb Strait",
            "Strait of Hormuz",
            "Gibraltar Strait",
        ],
    }
)
DISTANCES = pd.DataFrame(
    [
        {
            "origin_region": "MDE",
            "dest_region": "EUR",
            "passages": ["babalmandab", "gibraltar", "ormuz", "suez"],
        },
        {"origin_region": "NAM", "dest_region": "EUR", "passages": []},
        {"origin_region": "EUR", "dest_region": "EUR", "passages": []},
        {"origin_region": "MDE", "dest_region": "NAM", "passages": ["suez"]},
    ]
)
# Europe imports 40 t from the Middle East and 60 t from North America (plus 500 t within).
SOURCES = pd.DataFrame(
    [
        {
            "year": 2024,
            "importer_region": "EUR",
            "exporter_iso3": "SAU",
            "exporter_region": "MDE",
            "is_intra_regional": False,
            "qty_t": 40.0,
        },
        {
            "year": 2024,
            "importer_region": "EUR",
            "exporter_iso3": "USA",
            "exporter_region": "NAM",
            "is_intra_regional": False,
            "qty_t": 60.0,
        },
        {
            "year": 2024,
            "importer_region": "EUR",
            "exporter_iso3": "DEU",
            "exporter_region": "EUR",
            "is_intra_regional": True,
            "qty_t": 500.0,
        },
        {
            "year": 2023,
            "importer_region": "EUR",
            "exporter_iso3": "SAU",
            "exporter_region": "MDE",
            "is_intra_regional": False,
            "qty_t": 999.0,
        },
    ]
)


def routes() -> pd.DataFrame:
    table = exposure.route_chokepoints(DISTANCES, CONFIG.passage_chokepoints, CHOKEPOINTS, "EUR")
    return exposure.import_routes(SOURCES, table, "EUR", exposure.latest_year(SOURCES, "EUR"))


def test_routes_to_europe_with_readable_labels() -> None:
    table = exposure.route_chokepoints(DISTANCES, CONFIG.passage_chokepoints, CHOKEPOINTS, "EUR")
    by_region = table.set_index("origin_region")

    assert list(by_region.index) == ["MDE", "NAM"]  # no route within Europe, none to NAM
    assert by_region.loc["MDE", "route"] == "Hormuz · Bab el-Mandeb · Suez · Gibraltar"
    assert by_region.loc["NAM", "route"] == exposure.NO_CHOKEPOINT


def test_exposure_share_of_extra_regional_imports() -> None:
    table = routes()

    assert table["qty_t"].sum() == 100  # 2024 only, intra-European trade excluded
    assert exposure.exposure_share(table, {"chokepoint4"}) == pytest.approx(40.0)
    assert exposure.exposure_share(table, set()) == 0.0
    assert exposure.top_share(table, n=1) == pytest.approx(60.0)


def test_traffic_light_levels_on_both_sides_of_each_threshold() -> None:
    supply = CONFIG.signals.supply  # amber 10, red 25

    assert signals.level(9.9, supply) == signals.GREEN
    assert signals.level(10.0, supply) == signals.AMBER
    assert signals.level(24.9, supply) == signals.AMBER
    assert signals.level(25.0, supply) == signals.RED
    assert signals.level(None, supply) == signals.GREEN


def test_price_supply_and_logistics_signals() -> None:
    market = pd.DataFrame(
        [
            {"date": pd.Timestamp(d), "series_id": s, "name": s, "unit": "EUR/bbl", "value": v}
            for s, d, v in [
                ("DCOILBRENTEU", "2026-08-01", 70.0),
                ("DCOILBRENTEU", "2026-11-01", 80.0),
                ("GSCPI", "2026-10-31", 0.7),
            ]
        ]
    )

    price = signals.price_signal(market, CONFIG.signals)
    supply = signals.supply_signal(40.0, 6.8e6, 2024, CONFIG.signals)
    logistics = signals.logistics_signal(market, CONFIG.signals)

    assert (price.value, price.level) == ("+14.3 %", signals.RED)  # 80 / 70 - 1
    assert (supply.value, supply.level) == ("40 %", signals.RED)
    assert (logistics.value, logistics.level) == ("+0.70", signals.AMBER)


def test_what_changed_lists() -> None:
    history = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-11-01", "2026-11-08"] * 2),
            "location_id": ["a", "a", "b", "b"],
            "location": ["A", "A", "B", "B"],
            "is_disrupted": [False, True, True, True],
        }
    )
    events = pd.DataFrame(
        {
            "from_date": pd.to_datetime(["2026-11-05", "2026-10-01", "2026-11-06"]),
            "alert_level": ["RED", "RED", "GREEN"],
        }
    )
    market = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-10-01", "2026-11-01"] * 2),
            "series_id": ["X", "X", "Y", "Y"],
            "name": ["X", "X", "Y", "Y"],
            "value": [100.0, 110.0, 100.0, 70.0],
        }
    )

    assert signals.newly_disrupted(history, 7)["location_id"].tolist() == ["a"]
    assert len(signals.new_events(events, pd.Timestamp("2026-11-08"), 7)) == 1
    assert signals.largest_moves(market)["series_id"].tolist() == ["Y", "X"]  # -30 % before +10 %
