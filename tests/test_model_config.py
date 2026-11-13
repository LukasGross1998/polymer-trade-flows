import pytest
from helpers import REPO_ROOT

from ptf.model.config import FreightAssumption, load_model_config
from ptf.regions import load_regions


def test_project_model_config_covers_every_region() -> None:
    config = load_model_config(REPO_ROOT / "config" / "model.yaml")
    regions = load_regions(REPO_ROOT / "config" / "regions.yaml")

    assert set(config.regions) == set(regions.regions)
    assert all(r.source for r in config.regions.values())
    assert config.penalty_usd_t > max(r.prod_cost_usd_t for r in config.regions.values())


def test_freight_is_fixed_plus_distance_and_zero_within_region() -> None:
    freight = FreightAssumption(source="test", fixed_usd_t=40, variable_usd_t_per_1000nm=7)

    assert freight.cost_usd_t(10_000) == pytest.approx(110.0)  # 40 + 7 * 10
    assert freight.cost_usd_t(0) == 0.0
