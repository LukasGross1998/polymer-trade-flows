"""Route scenarios (spec 014): resolution and route risk, hand-checkable numbers."""

import pandas as pd
import pytest
from helpers import REPO_ROOT

from ptf.insights import exposure, scenario
from ptf.insights.config import ScenarioSettings, load_sourcing_config

CONFIG = load_sourcing_config(REPO_ROOT / "config" / "sourcing.yaml")
SETTINGS = ScenarioSettings.model_validate(
    {
        "closed_below_pct": 50,
        "presets": {
            "red_sea_closed": {"label": "Red Sea closed", "closed": ["chokepoint4", "chokepoint1"]},
            "hormuz_closed": {"label": "Hormuz closed", "closed": ["chokepoint6"]},
        },
    }
)
DETOURS = {"chokepoint4": "babalmandab_closed", "chokepoint1": "suez_closed"}
# Monitor today: Hormuz -95 %, Bab el-Mandeb -58 %, Suez -30 % (flagged at -30 %).
STATUS = pd.DataFrame(
    {
        "location_id": ["chokepoint6", "chokepoint4", "chokepoint1", "chokepoint8"],
        "deviation_pct": [-95.0, -58.0, -30.0, 2.0],
        "is_disrupted": [True, True, True, False],
    }
)


def test_project_config_detours() -> None:
    assert "chokepoint6" not in CONFIG.chokepoint_detours  # Hormuz: no sea detour
    assert CONFIG.chokepoint_detours["chokepoint4"] == "babalmandab_closed"


def test_live_status_closes_and_reduces_chokepoints() -> None:
    live = scenario.resolve(scenario.LIVE, STATUS, SETTINGS, DETOURS)

    assert live.closed == {"chokepoint6", "chokepoint4"}
    assert live.reduced == {"chokepoint1"}
    assert live.variant == "babalmandab_closed"  # Hormuz has no detour variant


def test_presets_and_combined_variants() -> None:
    red_sea = scenario.resolve("red_sea_closed", STATUS, SETTINGS, DETOURS)
    hormuz = scenario.resolve("hormuz_closed", None, SETTINGS, DETOURS)

    assert red_sea.variant == "babalmandab_closed+suez_closed"
    assert red_sea.reduced == frozenset()
    assert hormuz.variant == scenario.BASE_VARIANT
    assert scenario.resolve("unknown", None, SETTINGS, DETOURS).key == scenario.LIVE
    assert [o["value"] for o in scenario.options(SETTINGS)] == [
        "live",
        "red_sea_closed",
        "hormuz_closed",
    ]


def test_routes_at_risk_delayed_or_reduced() -> None:
    live = scenario.resolve(scenario.LIVE, STATUS, SETTINGS, DETOURS)
    routes = pd.DataFrame(
        {
            "route_key": ["MDE", "SEA", "SAU:Yanbu", "NAM", "ROW"],
            # In the Bab el-Mandeb variant: the Gulf still passes Hormuz, Asia goes around the
            # Cape, Yanbu leaves north through Suez, the rest of the world has no route.
            "chokepoint_ids": [
                ["chokepoint6", "chokepoint7"],
                ["chokepoint7"],
                ["chokepoint1"],
                [],
                [],
            ],
            "distance_nm": [11045.0, 11855.0, 3500.0, 5038.0, float("nan")],
        }
    )
    base = pd.Series({"MDE": 6262.0, "SEA": 8367.0, "SAU:Yanbu": 3500.0, "NAM": 5038.0})

    table = scenario.classify(routes, base, live).set_index("route_key")

    assert table["at_risk"].tolist() == [True, False, False, False, False]
    assert table["delayed"].tolist() == [False, True, False, False, False]
    assert table.loc["SAU:Yanbu", "reduced"]  # Suez is only reduced


def test_country_with_two_ports_gives_a_range() -> None:
    rows = pd.DataFrame(
        {"exporter_iso3": ["SAU", "USA"], "exporter_region": ["MDE", "NAM"], "qty_t": [40.0, 60.0]}
    )
    keyed = exposure.with_route_keys(rows, {"SAU": ["SAU:Al Jubail", "SAU:Yanbu"]})

    assert keyed["route_key"].tolist() == ["SAU:Al Jubail", "SAU:Yanbu", "NAM"]
    assert keyed["n_ports"].tolist() == [2, 2, 1]
    at_risk = pd.Series([True, False, False])  # only the Gulf port is behind Hormuz
    assert exposure.share_range(keyed, at_risk) == pytest.approx((0.0, 40.0))
    assert exposure.country_tonnes(keyed).sum() == 100.0  # Saudi tonnes counted once


def test_destination_groups_and_other() -> None:
    bilateral = pd.DataFrame(
        {
            "year": 2024,
            "exporter_iso3": ["SAU", "SAU", "USA", "DEU"],
            "importer_iso3": ["TUR", "BEL", "XKX", "FRA"],
            "exporter_region": ["MDE", "MDE", "NAM", "EUR"],
            "importer_region": "EUR",
            "qty_t": [100.0, 50.0, 30.0, 999.0],
        }
    )
    groups = {"North-West Europe": ["BEL"], "Turkey": ["TUR"]}
    table = exposure.destination_tonnes(bilateral, "EUR", 2024, groups)
    by_key = table.set_index(["exporter_iso3", "destination"])["qty_t"]

    assert by_key[("SAU", "Turkey")] == 100.0
    assert by_key[("USA", "Other Europe")] == 30.0  # not listed in any group
    assert "DEU" not in set(table["exporter_iso3"])  # intra-European trade left out

    countries = pd.DataFrame(
        {"exporter_iso3": list("ABCD"), "exporter_name": list("ABCD"), "qty_t": [4.0, 3, 2, 1]}
    )
    top = exposure.top_with_other(countries, 2)
    assert top["exporter_name"].tolist() == ["A", "B", "Other (2 countries)"]
    assert top["qty_t"].tolist() == [4.0, 3.0, 3.0]
