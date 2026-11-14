"""Europe relevance and chokepoint dependency (spec 013), hand-checkable numbers."""

import pandas as pd
import pytest

from ptf.insights import relevance
from ptf.insights.config import Relevance as RelevanceConfig
from ptf.shipping.config import PortConfig

# Europe's extra-regional imports: Middle East 40 t (Hormuz, Bab el-Mandeb, Suez), North
# America 56 t (no chokepoint), Southeast Asia 4 t (Malacca, Bab el-Mandeb, Suez).
ROUTES = pd.DataFrame(
    {
        "exporter_region": ["MDE", "NAM", "SEA"],
        "qty_t": [40.0, 56.0, 4.0],
        "chokepoint_ids": [
            ["chokepoint6", "chokepoint4", "chokepoint1"],
            [],
            ["chokepoint5", "chokepoint4", "chokepoint1"],
        ],
    }
)
PORTS = [
    PortConfig(id="port481", name="Houston", role="", region="NAM"),
    PortConfig(id="port1188", name="Shanghai", role="", region="CHN"),
    PortConfig(id="port1114", name="Rotterdam", role="", region="EUR"),
]
CONFIG = RelevanceConfig(
    min_region_share=5.0, extra_chokepoints=["chokepoint9"], series=["DCOILBRENTEU"]
)


def test_relevant_regions_chokepoints_and_ports() -> None:
    result = relevance.build(ROUTES, "EUR", PORTS, CONFIG)

    assert result.regions == {"EUR", "MDE", "NAM"}  # Southeast Asia only 4 %
    assert result.chokepoints == {"chokepoint6", "chokepoint4", "chokepoint1", "chokepoint9"}
    assert "chokepoint5" not in result.chokepoints  # Malacca: only the 4 % from Southeast Asia
    assert result.ports == {"port481", "port1114"}  # not Shanghai


def test_events_near_relevant_points() -> None:
    points = pd.DataFrame({"lat": [12.6], "lon": [43.3]})  # Bab el-Mandeb
    events = pd.DataFrame({"lat": [15.0, 41.4], "lon": [42.0, 141.0]})  # Red Sea; Japan

    assert relevance.near_any(events, points, 1000).tolist() == [True, False]
    assert relevance.distance_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.01)


def test_chokepoint_dependency_uses_each_chokepoints_own_detour() -> None:
    # Spec 014: region A (100 t) passes Hormuz and Bab el-Mandeb, 6,000 nm open and 10,032 nm
    # with Bab el-Mandeb closed; region B (100 t) passes only Bab el-Mandeb, 8,000 / 12,032 nm.
    routes = pd.DataFrame(
        {
            "exporter_iso3": ["AAA", "BBB"],
            "exporter_region": ["A", "B"],
            "route_key": ["A", "B"],
            "qty_t": [100.0, 100.0],
            "chokepoint_ids": [["chokepoint6", "chokepoint4"], ["chokepoint4"]],
        }
    )
    base = pd.DataFrame(
        {"origin_region": ["A", "B"], "dest_region": "EUR", "distance_nm": [6000.0, 8000.0]}
    )
    detour = base.assign(distance_nm=[10032.0, 12032.0])
    tables = {"base": base, "babalmandab_closed": detour}

    table = relevance.chokepoint_dependency(
        routes, tables, {"chokepoint4": "babalmandab_closed"}, "EUR", 14
    ).set_index("chokepoint_id")

    # 4,032 nm / (14 kn x 24 h = 336 nm a day) = 12.0 extra days for both regions.
    assert table.loc["chokepoint4", "extra_days"] == pytest.approx(12.0)
    assert table.loc["chokepoint4", "share_pct"] == pytest.approx(100.0)
    # Hormuz has no sea detour: no extra days (the Red Sea detour is not its own).
    assert not table.loc["chokepoint6", "has_detour"]
    assert pd.isna(table.loc["chokepoint6", "extra_days"])
    assert table.loc["chokepoint6", "share_pct"] == pytest.approx(50.0)


def test_chokepoint_share_is_a_range_for_countries_with_several_ports() -> None:
    routes = pd.DataFrame(
        {
            "exporter_iso3": ["SAU", "SAU", "USA"],
            "exporter_region": ["MDE", "MDE", "NAM"],
            "route_key": ["SAU:Al Jubail", "SAU:Yanbu", "NAM"],
            "qty_t": [40.0, 40.0, 60.0],  # Saudi tonnes appear once per port
            "chokepoint_ids": [["chokepoint6", "chokepoint4"], ["chokepoint4"], []],
        }
    )
    base = pd.DataFrame(
        {
            "origin_region": ["SAU:Al Jubail", "SAU:Yanbu", "NAM"],
            "dest_region": "EUR",
            "distance_nm": [6300.0, 3500.0, 5000.0],
        }
    )

    table = relevance.chokepoint_dependency(routes, {"base": base}, {}, "EUR", 14).set_index(
        "chokepoint_id"
    )

    # Hormuz: 0 t if all Saudi PE leaves from Yanbu, 40 of 100 t if all from Al Jubail.
    assert table.loc["chokepoint6", "share_low_pct"] == 0.0
    assert table.loc["chokepoint6", "share_pct"] == pytest.approx(40.0)
    assert table.loc["chokepoint4", "share_low_pct"] == pytest.approx(40.0)  # both ports
