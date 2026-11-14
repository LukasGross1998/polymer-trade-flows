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
    supply = CONFIG.signals.supply  # yellow 10, orange 25, red 50

    assert signals.level(9.9, supply) == signals.GREEN
    assert signals.level(10.0, supply) == signals.YELLOW
    assert signals.level(24.9, supply) == signals.YELLOW
    assert signals.level(25.0, supply) == signals.ORANGE
    assert signals.level(49.9, supply) == signals.ORANGE
    assert signals.level(50.0, supply) == signals.RED
    assert signals.level(None, supply) == signals.GREEN

    # Today's data (spec 013): price +27 %, exposure 52 %, GSCPI 1.26 -> not three times red.
    levels = [
        signals.level(27.0, CONFIG.signals.price),
        signals.level(52.0, supply),
        signals.level(1.26, CONFIG.signals.logistics),
    ]
    assert levels == [signals.ORANGE, signals.RED, signals.ORANGE]


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
    supply = signals.supply_signal(
        (40.0, 40.0), (30.0, 30.0), (10.0, 10.0), 6.8e6, 2024, "Live status", CONFIG.signals
    )
    ranged = signals.supply_signal(
        (16.0, 39.0), (16.0, 39.0), (0.0, 0.0), 6.8e6, 2024, "Hormuz closed", CONFIG.signals
    )
    logistics = signals.logistics_signal(market, CONFIG.signals)

    assert (price.value, price.level) == ("+14.3 %", signals.YELLOW)  # 80 / 70 - 1
    assert (supply.value, supply.level) == ("40 %", signals.ORANGE)
    assert supply.note.startswith("at risk 30 % (no sea detour), on a detour 10 %")
    assert (ranged.value, ranged.level) == ("16–39 %", signals.ORANGE)  # level: upper bound
    assert (logistics.value, logistics.level) == ("+0.70", signals.YELLOW)


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
            "date": pd.to_datetime(
                ["2026-10-25", "2026-11-01", "2026-10-25", "2026-11-01", "2026-10-01", "2026-11-01"]
            ),
            "series_id": ["X", "X", "Y", "Y", "Z", "Z"],
            "name": ["X", "X", "Y", "Y", "Z", "Z"],
            "frequency": "daily",
            "value": [100.0, 110.0, 100.0, 70.0, 100.0, 200.0],
        }
    )

    assert signals.newly_disrupted(history, 7)["location_id"].tolist() == ["a"]
    assert len(signals.new_events(events, pd.Timestamp("2026-11-08"), 7)) == 1
    # 7-day moves only: Z has no value 7-11 days back (its +100 % is a 31-day move).
    assert signals.largest_moves(market)["series_id"].tolist() == ["Y", "X"]  # -30 %, +10 %
    assert signals.largest_moves(market, series_ids=["X"])["series_id"].tolist() == ["X"]
    monthly = market.assign(frequency="monthly")
    assert signals.largest_moves(monthly).empty


def test_sources_for_one_grade() -> None:
    from ptf.insights.view import sources_for_grade

    base = {"year": 2024, "importer_region": "EUR", "is_intra_regional": False}
    by_product = pd.DataFrame(
        [
            {
                **base,
                "exporter_iso3": "SAU",
                "exporter_name": "Saudi Arabia",
                "exporter_region": "MDE",
                "hs6": "390120",
                "qty_t": 30.0,
                "value_usd": 30_000.0,
            },
            {
                **base,
                "exporter_iso3": "SAU",
                "exporter_name": "Saudi Arabia",
                "exporter_region": "MDE",
                "hs6": "390110",
                "qty_t": 10.0,
                "value_usd": 13_000.0,
            },
            {
                **base,
                "exporter_iso3": "USA",
                "exporter_name": "USA",
                "exporter_region": "NAM",
                "hs6": "390110",
                "qty_t": 60.0,
                "value_usd": 72_000.0,
            },
        ]
    )

    hdpe = sources_for_grade(by_product, "390120")
    everything = sources_for_grade(by_product).set_index("exporter_iso3")

    assert hdpe["exporter_iso3"].tolist() == ["SAU"]  # the USA ship no HDPE here
    assert hdpe["value_usd"].iloc[0] / hdpe["qty_t"].iloc[0] == 1000.0  # HDPE price only
    assert everything.loc["SAU", "qty_t"] == 40.0
    table = exposure.route_chokepoints(DISTANCES, CONFIG.passage_chokepoints, CHOKEPOINTS, "EUR")
    routes_hdpe = exposure.import_routes(hdpe, table, "EUR", 2024)
    assert exposure.exposure_share(routes_hdpe, {"chokepoint4"}) == 100.0
