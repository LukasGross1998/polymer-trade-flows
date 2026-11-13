import pytest

from ptf.core.regions import Port, RegionConfig
from ptf.model.distances import build_distance_table, port_distance_nm, sea_route

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
