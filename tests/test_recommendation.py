"""Recommendation logic (spec 016): sourceable origins, price ranges, confidence, timing."""

from datetime import date

import pandas as pd
import pytest
from helpers import REPO_ROOT

from ptf.insights import confidence, planner, sourceable
from ptf.insights.config import ConfidenceSettings, LeadTime, load_sourcing_config
from ptf.insights.view import CostQuotes, enrich

CONFIG = load_sourcing_config(REPO_ROOT / "config" / "sourcing.yaml")
SETTINGS = ConfidenceSettings()  # medium / low from 5 / 15 % mix effect, 2 / 3 years


def test_sanctioned_and_minor_origins() -> None:
    countries = pd.DataFrame({"exporter_iso3": ["IRN", "USA", "XXX"], "qty_t": [3e5, 2e6, 5e3]})
    table = sourceable.classify(countries, CONFIG).set_index("exporter_iso3")

    assert not table.loc["IRN", "sourceable"]
    assert "267/2012" in table.loc["IRN", "sourceable_reason"]  # TARIC import control
    assert table.loc["USA", "sourceable"] and not table.loc["USA", "minor"]
    assert table.loc["XXX", "minor"]  # 5,000 t below the 10,000 t limit

    blocked = CONFIG.model_copy(
        update={"sourceable": CONFIG.sourceable.model_copy(update={"blocked": {"USA": "policy"}})}
    )
    assert sourceable.classify(countries, blocked).set_index("exporter_iso3").loc[
        "USA", "sourceable_reason"
    ] == ("blocked: policy")


def by_product() -> pd.DataFrame:
    base = {"year": 2024, "importer_region": "EUR"}
    rows = [
        # Country AAA: grade A 100 t at 1,000 USD/t, grade B 300 t at 1,200 USD/t.
        {**base, "exporter_iso3": "AAA", "hs6": "A", "qty_t": 100.0, "value_usd": 100_000.0},
        {**base, "exporter_iso3": "AAA", "hs6": "B", "qty_t": 300.0, "value_usd": 360_000.0},
        # Another origin makes Europe's extra-regional mix 50/50: A 400 t, B 400 t in total.
        {**base, "exporter_iso3": "BBB", "hs6": "A", "qty_t": 300.0, "value_usd": 330_000.0},
        {**base, "exporter_iso3": "BBB", "hs6": "B", "qty_t": 100.0, "value_usd": 120_000.0},
        # Within Europe: A at 1,100, B at 1,150 USD/t.
        {**base, "exporter_iso3": "DEU", "hs6": "A", "qty_t": 10.0, "value_usd": 11_000.0},
        {**base, "exporter_iso3": "DEU", "hs6": "B", "qty_t": 10.0, "value_usd": 11_500.0},
    ]
    table = pd.DataFrame(rows)
    return table.assign(is_intra_regional=table["exporter_iso3"] == "DEU")


def test_price_range_and_mix_adjustment() -> None:
    ranges = confidence.price_ranges(by_product(), "EUR", 2024, 10).set_index("exporter_iso3")
    aaa = ranges.loc["AAA"]

    assert (aaa["price_low"], aaa["price_high"]) == (1000.0, 1200.0)
    assert aaa["unit_value"] == pytest.approx(1150.0)  # 460,000 / 400 t
    assert aaa["mix_adjusted"] == pytest.approx(1100.0)  # Europe's mix 50/50
    assert aaa["mix_effect"] == pytest.approx(50.0)


def test_difference_to_europe_per_grade_with_duty() -> None:
    prices = confidence.grade_prices(by_product(), "EUR", 2024)
    reference = confidence.reference_grade_prices(by_product(), "EUR", 2024)

    # A: 1,000 x 1.065 - 1,100 = -35; B: 1,200 x 1.065 - 1,150 = +128.
    low, high = confidence.europe_difference(prices, reference, "AAA", 6.5, 10)  # type: ignore[misc]
    assert (low, high) == pytest.approx((-35.0, 128.0))


@pytest.mark.parametrize(
    ("qty_t", "mix_pct", "age", "expected"),
    [
        (50_000, 4.9, 1, confidence.HIGH),
        (50_000, 5.0, 1, confidence.MEDIUM),
        (50_000, -15.0, 1, confidence.LOW),
        (50_000, 0.0, 2, confidence.MEDIUM),
        (50_000, 0.0, 3, confidence.LOW),
        (9_999, 0.0, 1, confidence.LOW),
    ],
)
def test_confidence_on_both_sides_of_each_threshold(
    qty_t: float, mix_pct: float, age: int, expected: str
) -> None:
    assert confidence.level(qty_t, mix_pct, age, 10_000, SETTINGS)[0] == expected


SOURCE = {"source": "test source", "url": "https://example.org/test", "read": "2026-11-14"}
LEAD = LeadTime.model_validate(
    {
        "vessel_size": "big",
        "speed_knots": {**SOURCE, "values": {"big": 15.0}},
        "port_days": {**SOURCE, "values": {"USA": 1.0, "IRN": 1.0, "NLD": 1.0}},
        "container_payload_t": {**SOURCE, "value": 26.5},
        "destination_country": "NLD",
        "default_need_by_days": 45,
        "default_quantity_t": 500,
    }
)


def test_latest_order_date_own_days_and_containers() -> None:
    landed = pd.DataFrame(
        {
            "exporter_iso3": ["USA"],
            "exporter_region": ["NAM"],
            "landed_eur_t": [1000.0],
            "sourceable": [True],
        }
    )
    leads = pd.DataFrame(
        {
            "origin_region": ["NAM"],
            "distance_nm": [0.0],
            "sea_days": [13.0],  # + 1 + 1 port days = 15 days transit
            "congested": [False],
            "storm_on_route": [False],
        }
    )
    args = (landed, leads, pd.Timestamp("2026-11-14"), pd.Timestamp("2026-12-31"), 500, LEAD)
    table = planner.plan(*args, True, own_before_days=4, own_after_days=6)

    # 31 Dec - (4 + 15 + 6 = 25 days) = 6 Dec; 500 t / 26.5 t = 18.9 -> at least 19 boxes.
    assert table.loc[0, "latest_order"] == pd.Timestamp("2026-12-06")
    assert table.loc[0, "arrival"] == pd.Timestamp("2026-12-03")  # ship: 14 Nov + 4 + 15
    assert table.loc[0, "at_site"] == pd.Timestamp("2026-12-09")
    assert table.loc[0, "containers"] == 19
    assert table.loc[0, "recommended"]


def test_not_sourceable_origin_is_never_recommended() -> None:
    landed = pd.DataFrame(
        {
            "exporter_iso3": ["IRN", "USA"],
            "exporter_region": ["MDE", "NAM"],
            "landed_eur_t": [900.0, 1000.0],
            "sourceable": [False, True],
        }
    )
    leads = pd.DataFrame(
        {
            "origin_region": ["MDE", "NAM"],
            "distance_nm": [0.0, 0.0],
            "sea_days": [13.0, 13.0],
            "congested": [False, False],
            "storm_on_route": [False, False],
        }
    )
    table = planner.plan(
        landed, leads, pd.Timestamp("2026-11-14"), pd.Timestamp("2026-12-31"), 500, LEAD, True
    ).set_index("exporter_iso3")

    assert not table.loc["IRN", "recommended"]  # cheaper and on time, but sanctioned
    assert table.loc["USA", "recommended"]


def test_capital_in_transit_and_own_quotes() -> None:
    table = pd.DataFrame(
        {
            "exporter_iso3": ["USA"],
            "exporter_region": ["NAM"],
            "qty_t": [50_000.0],
            "distance_nm": [9720.0],  # 27 sea days at 15 kn
            "price_eur_t": [1000.0],
            "duty_pct": [0.0],
            "landed_eur_t": [1000.0],
        }
    )
    config = CONFIG.model_copy(update={"lead_time": LEAD})
    quotes = CostQuotes(insurance_pct=0.1, handling_eur_t=12.0)

    enriched, missing = enrich(
        table,
        table[["exporter_iso3", "qty_t"]],
        None,
        config,
        2024,
        1.0,
        4.0,
        quotes,
        False,
        date(2026, 11, 14),
    )
    row = enriched.iloc[0]

    # 1 + 27 + 1 = 29 transit days; 1,000 x 4 % x 29 / 365 = 3.18 EUR/t.
    assert row["transit_days"] == pytest.approx(29.0)
    assert row["capital_eur_t"] == pytest.approx(3.178, abs=0.001)
    assert row["insurance_eur_t"] == pytest.approx(1.0)
    assert row["total_eur_t"] == pytest.approx(1000 + 3.178 + 1.0 + 12.0, abs=0.001)
    assert "on-carriage (no quote entered)" in missing
    assert "sea freight (no sourced rate)" in missing


def test_capital_formula_from_the_spec() -> None:
    # 1,000 EUR/t at 4 % for 30 days = 3.29 EUR/t.
    assert pytest.approx(3.29, abs=0.005) == 1000 * 4 / 100 * 30 / 365
