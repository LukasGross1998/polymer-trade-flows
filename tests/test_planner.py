"""Order planner (spec 010, sourced inputs since spec 015): hand-checkable numbers."""

import pandas as pd
import pytest
from helpers import REPO_ROOT

from ptf.insights import planner
from ptf.insights.config import LeadTime, load_sourcing_config

PROJECT_LEAD = load_sourcing_config(REPO_ROOT / "config" / "sourcing.yaml").lead_time
SOURCE = {"source": "test source", "url": "https://example.org/test", "read": "2026-11-14"}
LEAD = LeadTime.model_validate(
    {
        "vessel_size": "big",
        "speed_knots": {**SOURCE, "values": {"big": 15.0}},
        "port_days": {**SOURCE, "values": {"USA": 1.0, "KOR": 0.5, "NLD": 1.0}},
        "destination_country": "NLD",
        "default_need_by_days": 45,
        "default_quantity_t": 500,
    }
)
ROUTES = pd.DataFrame(
    {
        "origin_region": ["MDE", "NAM"],
        "distance_nm": [7200.0, 5400.0],
        "chokepoint_ids": [["chokepoint6", "chokepoint4", "chokepoint1"], []],
    }
)


def test_project_lead_time_uses_sourced_values() -> None:
    assert PROJECT_LEAD.speed == 16.3  # IMO: 8000-11999 TEU container ships, 2018
    assert PROJECT_LEAD.port_days.get("NLD") == pytest.approx(0.8007)  # UNCTAD 2023
    assert PROJECT_LEAD.port_days.get("SAU") is None  # not in UNCTAD's 22 economies


def test_vessel_size_must_have_a_sourced_speed() -> None:
    with pytest.raises(ValueError, match="no sourced speed"):
        LeadTime.model_validate({**LEAD.model_dump(), "vessel_size": "unknown"})


def test_sea_days_and_flags() -> None:
    leads = planner.lead_times(ROUTES, "EUR", LEAD, {"MDE"}, {"chokepoint4"})
    by_region = leads.set_index("origin_region")

    # 7,200 nm / (15 kn x 24 h) = 20 days at sea; no added days for congestion or storms.
    assert by_region.loc["MDE", "sea_days"] == pytest.approx(20.0)
    assert by_region.loc["NAM", "sea_days"] == pytest.approx(15.0)
    assert by_region.loc["MDE", "congested"] and by_region.loc["MDE", "storm_on_route"]
    assert not by_region.loc["NAM", "congested"]


def landed() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "exporter_iso3": ["SAU", "KOR", "USA"],
            "exporter_name": ["Saudi Arabia", "Korea", "USA"],
            "exporter_region": ["MDE", "NEA", "NAM"],
            "landed_eur_t": [900.0, 1000.0, 1100.0],
        }
    )


LEADS = pd.DataFrame(
    {
        "origin_region": ["MDE", "NEA", "NAM"],
        "distance_nm": [0.0, 0.0, 0.0],
        "sea_days": [20.0, 30.0, 15.0],
        "congested": [False, False, False],
        "storm_on_route": [False, False, False],
    }
)


def test_transit_time_arrival_and_unknown_port_data() -> None:
    table = planner.plan(
        landed(), LEADS, pd.Timestamp("2026-11-14"), pd.Timestamp("2026-12-01"), 500, LEAD, True
    ).set_index("exporter_iso3")

    # USA: 1.0 port day + 15 sea days + 1.0 in the Netherlands = 17 days -> 1 Dec.
    assert table.loc["USA", "lead_days"] == pytest.approx(17.0)
    assert table.loc["USA", "arrival"] == pd.Timestamp("2026-12-01")
    assert table.loc["USA", "on_time"] is True
    assert table.loc["KOR", "on_time"] is False  # 0.5 + 30 + 1 = 31.5 days
    # Saudi Arabia has no UNCTAD port time: no arrival, on time unknown.
    assert pd.isna(table.loc["SAU", "lead_days"])
    assert pd.isna(table.loc["SAU", "arrival"])
    assert table.loc["SAU", "on_time"] is None
    assert table.loc["USA", "total_eur"] == 550_000.0


def test_recommendation_only_with_known_freight_and_known_arrival() -> None:
    args = (landed(), LEADS, pd.Timestamp("2026-11-14"), pd.Timestamp("2026-12-31"), 500, LEAD)

    with_freight = planner.plan(*args, True).set_index("exporter_iso3")
    # Saudi Arabia is cheapest but its arrival is unknown: Korea is the cheapest on time.
    assert with_freight["recommended"].idxmax() == "KOR"

    without_freight = planner.plan(*args, False)
    assert not without_freight["recommended"].any()


def test_transit_range_from_the_ship_speed_table() -> None:
    # Spec 018: 9,720 nm takes 24.5 days at 16.5 kn and 34.3 days at 11.8 kn.
    fast, slow = planner.sea_day_range(9720 / (16.3 * 24), 16.3, PROJECT_LEAD)
    assert (round(fast, 1), round(slow, 1)) == (24.5, 34.3)
