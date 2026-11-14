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


def test_chokepoint_dependency_share_and_detour_days() -> None:
    open_routes = pd.DataFrame(
        {
            "origin_region": ["MDE", "NAM", "SEA"],
            "dest_region": "EUR",
            "distance_nm": [6262.0, 5038.0, 8367.0],
        }
    )
    closed = open_routes.assign(distance_nm=[11045.0, 5038.0, 11855.0])

    table = relevance.chokepoint_dependency(ROUTES, open_routes, closed, "EUR", 14).set_index(
        "chokepoint_id"
    )

    assert table.loc["chokepoint4", "share_pct"] == pytest.approx(44.0)  # 40 + 4 of 100 t
    # Detour days at 14 kn: MDE (11,045 - 6,262) / 336 = 14.2; SEA 10.4; weighted 13.9.
    assert table.loc["chokepoint4", "extra_days"] == pytest.approx(13.9, abs=0.05)
    assert table.loc["chokepoint5", "share_pct"] == pytest.approx(4.0)
