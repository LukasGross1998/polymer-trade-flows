"""Typed access to `config/sourcing.yaml` (focus region, chokepoint mapping, thresholds)."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class Threshold(BaseModel):
    """A traffic light with four levels: yellow, orange and red from these values (inclusive)."""

    yellow: float
    orange: float
    red: float


class PriceSignal(Threshold):
    series: str
    days: int


class LogisticsSignal(Threshold):
    series: str


class Signals(BaseModel):
    price: PriceSignal
    supply: Threshold
    logistics: LogisticsSignal


class PreferentialDuty(BaseModel):
    pct: float
    source: str


class Duty(BaseModel):
    default_pct: float
    preferential: dict[str, PreferentialDuty] = {}

    def rate_pct(self, iso3: str) -> float:
        """EU import duty for goods from `iso3`, in % of the customs value (CIF)."""
        preference = self.preferential.get(iso3)
        return preference.pct if preference is not None else self.default_pct


class LandedCostSettings(BaseModel):
    top_n: int
    fx_series: str
    resin_index: str
    duty: Duty


class LeadTime(BaseModel):
    """Assumptions of the order planner (spec 010), in days and knots."""

    speed_knots: float
    origin_port_days: float
    destination_port_days: float
    congestion_buffer_days: float
    storm_buffer_days: float
    europe_days: float
    default_need_by_days: int
    default_quantity_t: float
    overland_days: dict[str, float] = {}


class Relevance(BaseModel):
    """What counts as relevant for the focus region's buyer (spec 013)."""

    min_region_share: float = 5.0
    extra_chokepoints: list[str] = []
    event_radius_km: float = 1000.0
    series: list[str] = []


class SourcingConfig(BaseModel):
    focus_region: str
    passage_chokepoints: dict[str, str]
    signals: Signals
    recent_days: int
    landed_cost: LandedCostSettings
    lead_time: LeadTime
    relevance: Relevance = Relevance()


def load_sourcing_config(path: Path) -> SourcingConfig:
    with path.open(encoding="utf-8") as f:
        return SourcingConfig.model_validate(yaml.safe_load(f))
