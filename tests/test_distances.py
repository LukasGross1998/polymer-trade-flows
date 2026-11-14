from pathlib import Path

import pytest

from ptf.core.regions import Port, RegionConfig
from ptf.model.distances import (
    build_distance_table,
    ingest_route_variants,
    port_distance_nm,
    read_distance_table,
    sea_route,
)

ROTTERDAM = Port(name="Rotterdam", lon=4.05, lat=51.95)
SHANGHAI = Port(name="Shanghai", lon=121.8, lat=31.2)


@pytest.mark.slow
def test_rotterdam_shanghai_is_plausible() -> None:
    # Via Suez the real route is roughly 10,500 nm.
    assert 9_500 < port_distance_nm(ROTTERDAM, SHANGHAI) < 11_500


@pytest.mark.slow
def test_blocking_suez_forces_longer_route_around_the_cape() -> None:
    via_suez = port_distance_nm(ROTTERDAM, SHANGHAI)
    via_cape = port_distance_nm(ROTTERDAM, SHANGHAI, restrictions=["northwest", "suez"])

    assert via_cape > via_suez + 2_000


@pytest.mark.slow
def test_distance_table_covers_all_pairs_with_zero_on_diagonal() -> None:
    regions = RegionConfig.model_validate(
        {
            "rest_of_world": "ROW",
            "regions": {
                "EUR": {"name": "Europe", "port": ROTTERDAM.model_dump(), "reporters": ["DEU"]},
                "CHN": {"name": "China", "port": SHANGHAI.model_dump(), "reporters": ["CHN"]},
            },
        }
    )

    table = build_distance_table(regions).set_index(["origin_region", "dest_region"])

    assert len(table) == 4
    assert table.loc[("EUR", "EUR"), "distance_nm"] == 0
    assert table.loc[("EUR", "CHN"), "distance_nm"] > 0
    assert list(table.loc[("EUR", "EUR"), "passages"]) == []
    assert "suez" in table.loc[("CHN", "EUR"), "passages"]


@pytest.mark.slow
def test_route_passages_middle_east_and_north_america_to_europe() -> None:
    jebel_ali = Port(name="Jebel Ali", lon=55.0, lat=25.0)
    houston = Port(name="Houston", lon=-95.0, lat=29.7)

    _, gulf = sea_route(jebel_ali, ROTTERDAM)
    _, atlantic = sea_route(houston, ROTTERDAM)

    assert gulf == ["babalmandab", "gibraltar", "ormuz", "suez"]
    assert atlantic == []


@pytest.mark.slow
def test_red_sea_closed_variant_goes_around_the_cape(tmp_path: Path) -> None:
    regions = RegionConfig.model_validate(
        {
            "rest_of_world": "ROW",
            "regions": {
                "EUR": {"name": "Europe", "port": ROTTERDAM.model_dump(), "reporters": ["DEU"]},
                "MDE": {
                    "name": "Middle East",
                    "port": {"name": "Jebel Ali", "lon": 55.0, "lat": 25.0},
                    "reporters": ["ARE"],
                },
                "NAM": {
                    "name": "North America",
                    "port": {"name": "Houston", "lon": -95.0, "lat": 29.7},
                    "reporters": ["USA"],
                },
            },
        }
    )
    closed = ["northwest", "suez", "babalmandab", "panama"]

    (path,) = ingest_route_variants(regions, tmp_path, {"red_sea_closed": closed})
    table = read_distance_table(tmp_path, "red_sea_closed")

    assert path.name == "sea_distances_red_sea_closed.parquet"
    assert table is not None
    by_pair = table.set_index(["origin_region", "dest_region"])
    assert 10_500 < by_pair.loc[("MDE", "EUR"), "distance_nm"] < 11_500  # 6,262 nm via Suez
    assert "south_africa" in list(by_pair.loc[("MDE", "EUR"), "passages"])
    assert 4_500 < by_pair.loc[("NAM", "EUR"), "distance_nm"] < 5_500  # Atlantic, unchanged


@pytest.mark.slow
def test_country_ports_and_routes_without_a_sea_path() -> None:
    from ptf.core.regions import RegionConfig as Regions

    regions = Regions.model_validate(
        {
            "rest_of_world": "ROW",
            "regions": {
                "EUR": {"name": "Europe", "port": ROTTERDAM.model_dump(), "reporters": ["DEU"]},
                "AFR": {
                    "name": "Africa",
                    "port": {"name": "Durban", "lon": 31.05, "lat": -29.9},
                    "reporters": ["ZAF"],
                },
            },
        }
    )
    alexandria = Port(name="Alexandria", lon=29.87, lat=31.19)
    table = build_distance_table(regions, None, {"EGY": [alexandria]}).set_index(
        ["origin_region", "dest_region"]
    )

    # Spec 014: Egypt ships from the Mediterranean, through Gibraltar, not around the Cape.
    egypt = table.loc[("EGY:Alexandria", "EUR")]
    assert "gibraltar" in egypt["passages"] and "south_africa" not in egypt["passages"]
    assert egypt["distance_nm"] < table.loc[("AFR", "EUR"), "distance_nm"]

    # Out of the Gulf with Hormuz blocked there is no sea path: NaN, not 0.
    jebel_ali = Port(name="Jebel Ali", lon=55.0, lat=25.0)
    distance, passages = sea_route(jebel_ali, ROTTERDAM, ["northwest", "ormuz"])
    assert distance != distance and passages == []  # NaN
