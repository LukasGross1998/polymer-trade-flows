import pytest
from helpers import REPO_ROOT, sourced
from pydantic import ValidationError

from ptf.core.regions import load_regions
from ptf.model.config import FreightAssumption, ModelConfig, load_model_config


def test_project_model_config_covers_every_region_and_lp_is_off() -> None:
    config = load_model_config(REPO_ROOT / "config" / "model.yaml")
    regions = load_regions(REPO_ROOT / "config" / "regions.yaml")

    assert set(config.regions) == set(regions.regions)
    # Spec 015: freight, utilisation and costs have no source, so the LP must stay off.
    assert not config.enabled
    assert "freight" in config.missing_inputs()
    assert config.regions["NAM"].capacity_mt is not None
    assert config.regions["NAM"].capacity_mt.value == 34


def test_enabling_the_lp_needs_every_input_sourced() -> None:
    with pytest.raises(ValidationError, match="freight"):
        ModelConfig.model_validate(
            {"enabled": True, "base_year": 2023, "penalty_usd_t": 5000, "regions": {"A": {}}}
        )


def test_a_fact_without_source_does_not_load() -> None:
    with pytest.raises(ValidationError):
        FreightAssumption.model_validate(
            {"fixed_usd_t": 40, "variable_usd_t_per_1000nm": sourced(7)}
        )


def test_freight_is_fixed_plus_distance_and_zero_within_region() -> None:
    freight = FreightAssumption.model_validate(
        {"fixed_usd_t": sourced(40), "variable_usd_t_per_1000nm": sourced(7)}
    )

    assert freight.cost_usd_t(10_000) == pytest.approx(110.0)  # 40 + 7 * 10
    assert freight.cost_usd_t(0) == 0.0
