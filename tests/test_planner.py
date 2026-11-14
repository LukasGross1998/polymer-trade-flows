"""Order planner (spec 010): lead times and the recommendation, hand-checkable numbers."""

from pathlib import Path

import pandas as pd
import pytest

from ptf.insights import planner
from ptf.insights.config import load_sourcing_config

LEAD = load_sourcing_config(
    Path(__file__).resolve().parents[1] / "config" / "sourcing.yaml"
).lead_time
ROUTES = pd.DataFrame(
    {
        "origin_region": ["MDE", "NAM"],
        "distance_nm": [6262.0, 5038.0],
        "chokepoint_ids": [["chokepoint6", "chokepoint4", "chokepoint1"], []],
    }
)


def test_sea_days_and_lead_time() -> None:
    leads = planner.lead_times(ROUTES, "EUR", LEAD, set(), set()).set_index("origin_region")

    # 6,262 nm / (14 kn x 24 h) = 18.6 days at sea + 4 + 4 port days.
    assert leads.loc["MDE", "sea_days"] == pytest.approx(18.64, abs=0.01)
    assert leads.loc["MDE", "lead_days"] == pytest.approx(26.64, abs=0.01)
    closed = ROUTES.assign(distance_nm=[11045.0, 5038.0])
    assert planner.lead_times(closed, "EUR", LEAD, set(), set())["lead_days"].iloc[
        0
    ] == pytest.approx(40.87, abs=0.01)


def test_buffers_for_congested_ports_and_storms() -> None:
    leads = planner.lead_times(ROUTES, "EUR", LEAD, {"MDE"}, {"chokepoint4"}).set_index(
        "origin_region"
    )
    assert leads.loc["MDE", "buffer_days"] == 5.0  # +3 congestion, +2 storm on the route
    assert leads.loc["NAM", "buffer_days"] == 0.0

    destination = planner.lead_times(ROUTES, "EUR", LEAD, {"EUR"}, set()).set_index("origin_region")
    assert destination["buffer_days"].tolist() == [3.0, 3.0]  # Rotterdam congested: all routes


def test_cheapest_on_time_supplier_is_recommended() -> None:
    landed = pd.DataFrame(
        {
            "exporter_iso3": ["CHN", "SAU", "USA"],
            "exporter_region": ["CHN", "MDE", "NAM"],
            "landed_eur_t": [900.0, 1000.0, 1100.0],
        }
    )
    leads = pd.DataFrame(
        {
            "origin_region": ["CHN", "MDE", "NAM"],
            "distance_nm": [0.0, 0.0, 0.0],
            "lead_days": [40.0, 27.0, 23.0],
        }
    )

    table = planner.plan(landed, leads, pd.Timestamp("2026-11-14"), pd.Timestamp("2026-12-15"), 500)
    by_country = table.set_index("exporter_iso3")

    assert not by_country.loc["CHN", "on_time"]  # arrives 24 Dec, after the need-by date
    assert by_country["recommended"].idxmax() == "SAU"  # cheapest of the on-time suppliers
    assert by_country.loc["SAU", "total_eur"] == 500_000.0
    assert by_country.loc["SAU", "arrival"] == pd.Timestamp("2026-12-11")

    late = planner.plan(landed, leads, pd.Timestamp("2026-11-14"), pd.Timestamp("2026-11-20"), 500)
    assert (
        late.set_index("exporter_iso3")["recommended"].idxmax() == "USA"
    )  # none on time: earliest


def test_overland_days_for_landlocked_exporters() -> None:
    landed = pd.DataFrame(
        {"exporter_iso3": ["UZB"], "exporter_region": ["CIS"], "landed_eur_t": [960.0]}
    )
    leads = pd.DataFrame({"origin_region": ["CIS"], "distance_nm": [0.0], "lead_days": [12.0]})

    table = planner.plan(
        landed, leads, pd.Timestamp("2026-11-14"), pd.Timestamp("2026-12-31"), 1, {"UZB": 21.0}
    )

    assert table.loc[0, "lead_days"] == 33.0  # 12 by sea from St. Petersburg + 21 by rail
    assert table.loc[0, "arrival"] == pd.Timestamp("2026-12-17")
