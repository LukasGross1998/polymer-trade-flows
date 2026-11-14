"""Landed cost per supplier country (spec 007) with hand-checkable numbers."""

from datetime import date

import pandas as pd
import pytest
from helpers import sourced

from ptf.insights import landed_cost
from ptf.insights.config import Duty
from ptf.model.config import FreightAssumption

FREIGHT = FreightAssumption.model_validate(
    {"fixed_usd_t": sourced(40), "variable_usd_t_per_1000nm": sourced(7)}
)
DUTY = Duty.model_validate(
    {
        "default_pct": sourced(6.5),
        "preferential": {"USA": sourced(0.0, valid_from="2026-07-01", valid_to="2026-12-31")},
    }
)
DISTANCES = pd.DataFrame(
    {
        "origin_region": ["MDE", "NAM", "EUR"],
        "dest_region": ["EUR", "EUR", "EUR"],
        "distance_nm": [6000.0, 5000.0, 0.0],
    }
)
SOURCES = pd.DataFrame(
    [
        # (iso3, region, intra, tonnes, value): Saudi Arabia 1,000 USD/t, USA 1,200 USD/t
        {
            "exporter_iso3": "SAU",
            "exporter_region": "MDE",
            "is_intra_regional": False,
            "qty_t": 100.0,
            "value_usd": 100_000.0,
        },
        {
            "exporter_iso3": "USA",
            "exporter_region": "NAM",
            "is_intra_regional": False,
            "qty_t": 50.0,
            "value_usd": 60_000.0,
        },
        {
            "exporter_iso3": "ROU",
            "exporter_region": "EUR",
            "is_intra_regional": True,
            "qty_t": 10.0,
            "value_usd": 15_000.0,
        },
        {
            "exporter_iso3": "XXX",
            "exporter_region": "ROW",
            "is_intra_regional": False,
            "qty_t": 1.0,
            "value_usd": 900.0,
        },
    ]
).assign(year=2024, importer_region="EUR", exporter_name=lambda f: f["exporter_iso3"])


def table(**kwargs: float) -> pd.DataFrame:
    prices = landed_cost.unit_prices(SOURCES, "EUR", 2024)
    result = landed_cost.landed_cost(prices, DISTANCES, FREIGHT, DUTY, "EUR", 1.10, **kwargs)
    return result.set_index("exporter_iso3")


def test_landed_cost_components() -> None:
    sau = table().loc["SAU"]

    assert sau["freight_usd_t"] == pytest.approx(82.0)  # 40 + 7 x 6
    assert sau["duty_usd_t"] == pytest.approx(70.33)  # 6.5 % of 1,082
    assert sau["landed_usd_t"] == pytest.approx(1152.33)
    assert sau["landed_eur_t"] == pytest.approx(1047.57, abs=0.01)  # / 1.10


def test_freight_factor_preference_and_rest_of_world() -> None:
    doubled = table(freight_factor=2.0)
    assert doubled.loc["SAU", "freight_usd_t"] == pytest.approx(164.0)
    assert doubled.loc["SAU", "duty_usd_t"] == pytest.approx(75.66)
    assert doubled.loc["SAU", "landed_usd_t"] == pytest.approx(1239.66)

    usa = table().loc["USA"]
    assert usa["duty_usd_t"] == 0.0  # preferential rate
    assert usa["landed_usd_t"] == pytest.approx(1200 + 75)  # 40 + 7 x 5
    assert "XXX" not in table().index  # no sea distance for the rest of the world


def test_without_sourced_freight_landed_is_price_plus_duty() -> None:
    prices = landed_cost.unit_prices(SOURCES, "EUR", 2024)
    sau = landed_cost.landed_cost(prices, DISTANCES, None, DUTY, "EUR", 1.0).set_index(
        "exporter_iso3"
    )
    sau = sau.loc["SAU"]

    assert pd.isna(sau["freight_usd_t"])  # n/a, not an estimate
    assert sau["duty_usd_t"] == pytest.approx(65.0)  # 6.5 % of the price alone
    assert sau["landed_usd_t"] == pytest.approx(1065.0)


def test_preference_only_inside_its_validity() -> None:
    assert DUTY.rate_pct("USA", date(2026, 11, 14)) == 0.0
    assert DUTY.rate_pct("USA", date(2026, 6, 30)) == 6.5  # before it started
    assert DUTY.rate_pct("USA", date(2027, 1, 1)) == 6.5  # expired
    assert DUTY.rate_pct("USA") == 0.0  # no date: as configured
    assert DUTY.rate_pct("SAU", date(2026, 11, 14)) == 6.5


def test_price_scale_reference_and_weighting() -> None:
    assert table(price_scale=1.10).loc["SAU", "price_usd_t"] == pytest.approx(1100.0)
    assert landed_cost.reference_price(SOURCES, "EUR", 2024) == pytest.approx(1500.0)
    full = table().reset_index()
    assert landed_cost.weighted_landed(full, "MDE") == pytest.approx(1047.57, abs=0.01)


def test_price_factor_latest_over_base_year_average() -> None:
    market = pd.DataFrame(
        {
            "series_id": "IDX",
            "date": pd.to_datetime(["2024-01-01", "2024-07-01", "2026-09-01"]),
            "value": [290.0, 310.0, 330.0],
        }
    )

    assert landed_cost.price_factor(market, "IDX", 2024) == pytest.approx(1.10)  # 330 / 300
    assert landed_cost.price_factor(market, "missing", 2024) == 1.0


def test_mfn_rate_per_grade_and_weighted_over_grades() -> None:
    from ptf.insights.view import ALL_GRADES, mfn_rate

    eu_duty = pd.DataFrame({"hs6": ["390110", "390120"], "mfn_pct": [6.5, 3.0]})
    base = {"year": 2024, "importer_region": "EUR", "is_intra_regional": False}
    by_product = pd.DataFrame(
        [{**base, "hs6": "390110", "qty_t": 30.0}, {**base, "hs6": "390120", "qty_t": 10.0}]
    )

    assert mfn_rate(eu_duty, by_product, "390120", "EUR") == 3.0
    assert mfn_rate(eu_duty, by_product, ALL_GRADES, "EUR") == pytest.approx(
        5.625
    )  # (6.5x30 + 3x10) / 40
    assert mfn_rate(None, by_product, "390120", "EUR") is None
    assert mfn_rate(eu_duty, by_product, "390190", "EUR") is None  # no WITS rate -> config
