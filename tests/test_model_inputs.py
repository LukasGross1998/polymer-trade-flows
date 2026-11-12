import pandas as pd
import pytest

from ptf.model.config import ModelConfig
from ptf.model.inputs import build_inputs, observed_region_flows, region_balance, route_costs


def make_config(**regions: tuple[float, float, float]) -> ModelConfig:
    """regions: code -> (capacity_mt, utilisation, prod_cost_usd_t)."""
    return ModelConfig.model_validate(
        {
            "base_year": 2023,
            "penalty_usd_t": 5000,
            "freight": {"source": "t", "fixed_usd_t": 40, "variable_usd_t_per_1000nm": 7},
            "regions": {
                code: {"capacity_mt": c, "utilisation": u, "prod_cost_usd_t": p, "source": "t"}
                for code, (c, u, p) in regions.items()
            },
        }
    )


def flow(year: int, exporter_region: str, importer_region: str, qty_t: float) -> dict:
    return {
        "year": year,
        "exporter_region": exporter_region,
        "importer_region": importer_region,
        "qty_t": qty_t,
    }


def test_observed_flows_are_summed_per_region_pair_and_year() -> None:
    flows = pd.DataFrame(
        [
            flow(2023, "MDE", "EUR", 100.0),
            flow(2023, "MDE", "EUR", 50.0),  # second country pair, same regions
            flow(2022, "MDE", "EUR", 999.0),  # other year
        ]
    )

    observed = observed_region_flows(flows, 2023)

    assert observed["qty_t"].tolist() == [150.0]


def test_demand_is_production_plus_imports_minus_exports() -> None:
    config = make_config(MDE=(1.0, 0.9, 500), EUR=(1.0, 0.5, 1200))
    observed = pd.DataFrame(
        [
            flow(2023, "MDE", "EUR", 300_000.0),
            flow(2023, "EUR", "EUR", 777_000.0),  # within a region: does not count
            flow(2023, "ROW", "EUR", 10_000.0),  # from rest of world: counts as import
        ]
    )

    balance = region_balance(observed, config).set_index("region")

    assert balance.loc["MDE", "demand_t"] == pytest.approx(900_000 - 300_000)
    assert balance.loc["EUR", "demand_t"] == pytest.approx(500_000 + 310_000)


def test_negative_demand_points_to_inconsistent_assumptions() -> None:
    config = make_config(MDE=(0.1, 1.0, 500), EUR=(1.0, 0.5, 1200))
    observed = pd.DataFrame([flow(2023, "MDE", "EUR", 300_000.0)])

    with pytest.raises(ValueError, match="MDE: observed exports"):
        region_balance(observed, config)


def test_route_cost_is_production_cost_plus_freight() -> None:
    config = make_config(MDE=(1.0, 0.9, 500), EUR=(1.0, 0.5, 1200))
    distances = pd.DataFrame(
        {
            "origin_region": ["MDE", "MDE", "ROW"],
            "dest_region": ["EUR", "MDE", "EUR"],
            "distance_nm": [6_000.0, 0.0, 1_000.0],
        }
    )

    costs = route_costs(distances, config).set_index(["origin_region", "dest_region"])

    assert ("ROW", "EUR") not in costs.index  # rest of world is not part of the LP
    assert costs.loc[("MDE", "EUR"), "unit_cost_usd_t"] == pytest.approx(500 + 40 + 42)
    assert costs.loc[("MDE", "MDE"), "unit_cost_usd_t"] == pytest.approx(500)


def test_build_inputs_exposes_delivered_cost() -> None:
    config = make_config(MDE=(1.0, 0.9, 500), EUR=(1.0, 0.5, 1200))
    distances = pd.DataFrame(
        {
            "origin_region": ["MDE", "MDE", "EUR", "EUR"],
            "dest_region": ["MDE", "EUR", "MDE", "EUR"],
            "distance_nm": [0.0, 6_000.0, 6_000.0, 0.0],
        }
    )
    balance = region_balance(pd.DataFrame([flow(2023, "MDE", "EUR", 1.0)]), config)

    inputs = build_inputs(balance, route_costs(distances, config), config)

    assert inputs.regions == ["MDE", "EUR"]
    assert inputs.unit_cost_usd_t("MDE", "EUR") == pytest.approx(582)
    assert inputs.capacity_t["MDE"] == pytest.approx(1_000_000)
