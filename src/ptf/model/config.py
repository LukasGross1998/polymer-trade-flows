"""Typed access to the model assumptions in `config/model.yaml`."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class FreightAssumption(BaseModel):
    source: str
    note: str = ""
    fixed_usd_t: float = Field(ge=0)
    variable_usd_t_per_1000nm: float = Field(ge=0)

    def cost_usd_t(self, distance_nm: float) -> float:
        """Freight per tonne for a sea distance; 0 within a region (distance 0)."""
        if distance_nm == 0:
            return 0.0
        return self.fixed_usd_t + self.variable_usd_t_per_1000nm * distance_nm / 1000


class RegionAssumption(BaseModel):
    capacity_mt: float = Field(ge=0)
    utilisation: float = Field(ge=0, le=1)
    prod_cost_usd_t: float = Field(ge=0)
    source: str

    @property
    def capacity_t(self) -> float:
        return self.capacity_mt * 1_000_000

    @property
    def production_t(self) -> float:
        """Assumed actual production: capacity x utilisation."""
        return self.capacity_t * self.utilisation


class RouteVariant(BaseModel):
    """Passages blocked in a variant of the sea-distance table (searoute names)."""

    source: str
    note: str = ""
    restrictions: list[str]


class ModelConfig(BaseModel):
    base_year: int
    penalty_usd_t: float = Field(gt=0)
    freight: FreightAssumption
    regions: dict[str, RegionAssumption]
    route_variants: dict[str, RouteVariant] = {}


def load_model_config(path: Path) -> ModelConfig:
    with path.open(encoding="utf-8") as f:
        return ModelConfig.model_validate(yaml.safe_load(f))
