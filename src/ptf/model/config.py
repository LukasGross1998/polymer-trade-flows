"""Typed access to the model inputs in `config/model.yaml` (spec 015: sourced values only).

Facts (freight rates, capacities, costs) are `Sourced` values with source, url and read date.
A fact without a source is left out; the transport LP then cannot run and stays switched off
(`enabled: false`) until all its inputs are sourced.
"""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from ptf.core.regions import Port
from ptf.core.sourced import Sourced


class FreightAssumption(BaseModel):
    """Sea freight per tonne: a fixed part plus a part per 1,000 nautical miles."""

    fixed_usd_t: Sourced
    variable_usd_t_per_1000nm: Sourced

    def cost_usd_t(self, distance_nm: float) -> float:
        """Freight per tonne for a sea distance; 0 within a region (distance 0)."""
        if distance_nm == 0:
            return 0.0
        return self.fixed_usd_t.value + self.variable_usd_t_per_1000nm.value * distance_nm / 1000


class RegionAssumption(BaseModel):
    """LP inputs of one region; each is a sourced value or missing (None)."""

    capacity_mt: Sourced | None = None
    utilisation: Sourced | None = None
    prod_cost_usd_t: Sourced | None = None

    def missing(self) -> list[str]:
        return [
            name
            for name in ("capacity_mt", "utilisation", "prod_cost_usd_t")
            if getattr(self, name) is None
        ]

    def _value(self, name: str) -> float:
        value = getattr(self, name)
        if value is None:
            raise ValueError(f"{name} has no sourced value; the LP cannot use this region")
        return float(value.value)

    @property
    def capacity_t(self) -> float:
        return self._value("capacity_mt") * 1_000_000

    @property
    def production_t(self) -> float:
        """Actual production: capacity x utilisation."""
        return self.capacity_t * self._value("utilisation")

    @property
    def cost_usd_t(self) -> float:
        return self._value("prod_cost_usd_t")


class RouteVariant(BaseModel):
    """Passages blocked in a variant of the sea-distance table (searoute names). A setting:
    the scenario a user wants to look at, not a claim about the world."""

    note: str = ""
    restrictions: list[str]


class CountryRoute(BaseModel):
    """A country that does not ship from its region's representative port (spec 014).

    `source` shows where the country's polyethylene is made / leaves from; the coordinates of
    each port are a setting (a point in the port that searoute snaps to the sea lane). With
    several ports and no sourced shares, views show a range instead of splitting the volume.
    """

    ports: list[Port] = Field(min_length=1)
    source: str = Field(min_length=3)
    url: str = Field(pattern=r"^https?://")
    read: date


class ModelConfig(BaseModel):
    enabled: bool = False  # setting: run the transport LP (needs all inputs sourced)
    base_year: int  # setting
    penalty_usd_t: float = Field(gt=0)  # setting: technical cost of unmet demand
    freight: FreightAssumption | None = None
    regions: dict[str, RegionAssumption]
    route_variants: dict[str, RouteVariant] = {}
    country_routes: dict[str, CountryRoute] = {}

    def country_ports(self) -> dict[str, list[Port]]:
        return {iso3: route.ports for iso3, route in self.country_routes.items()}

    def missing_inputs(self) -> list[str]:
        """Inputs the LP needs that have no sourced value, e.g. ['freight', 'SAM.capacity_mt']."""
        missing = [] if self.freight is not None else ["freight"]
        for code, region in self.regions.items():
            missing += [f"{code}.{name}" for name in region.missing()]
        return missing

    @model_validator(mode="after")
    def enabled_only_when_complete(self) -> "ModelConfig":
        if self.enabled and self.missing_inputs():
            raise ValueError(
                "the transport LP is enabled but inputs have no source: "
                + ", ".join(self.missing_inputs())
            )
        return self


def load_model_config(path: Path) -> ModelConfig:
    with path.open(encoding="utf-8") as f:
        return ModelConfig.model_validate(yaml.safe_load(f))
