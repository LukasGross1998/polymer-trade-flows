"""Typed access to `config/sourcing.yaml` (focus region, chokepoint mapping, thresholds)."""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

from ptf.core.sourced import Sourced, SourcedRate, SourcedTable


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


class Duty(BaseModel):
    """EU import duty: the third-country rate and the preferences found in TARIC (spec 015)."""

    default_pct: Sourced
    preferential: dict[str, SourcedRate] = {}

    def rate_pct(self, iso3: str, on: date | None = None) -> float:
        """EU import duty for goods from `iso3` on date `on`, in % of the customs value (CIF).

        A preference applies only inside the validity period TARIC gives for it.
        """
        preference = self.preferential.get(iso3)
        if preference is not None and on is not None:
            started = preference.valid_from is None or preference.valid_from <= on
            running = preference.valid_to is None or on <= preference.valid_to
            if not (started and running):
                preference = None
        return preference.value if preference is not None else self.default_pct.value

    def with_default(self, pct: float, source: str, url: str, read: date) -> "Duty":
        """The same preferences with another third-country rate (e.g. from WITS per grade)."""
        default = Sourced(value=pct, source=source, url=url, read=read)
        return self.model_copy(update={"default_pct": default})


class ImportControl(BaseModel):
    """An EU sanctions measure on imports from a country, as listed in TARIC."""

    regulation: str
    url: str
    read: date


class LandedCostSettings(BaseModel):
    top_n: int
    fx_series: str
    resin_index: str
    duty: Duty


class LeadTime(BaseModel):
    """Inputs of the order planner (spec 010, sourced values since spec 015).

    Ship transit time = median time in port at origin + sea days + median time in port at
    destination. Settings: the ship size whose speed is used, the destination country, the
    default need-by days and quantity.
    """

    vessel_size: str
    speed_knots: SourcedTable  # average speed at sea by container ship size (TEU)
    port_days: SourcedTable  # median time in port of container ships by country (ISO3)
    destination_country: str
    default_need_by_days: int
    default_quantity_t: float

    @model_validator(mode="after")
    def vessel_size_has_a_speed(self) -> "LeadTime":
        if self.speed_knots.get(self.vessel_size) is None:
            raise ValueError(f"no sourced speed for vessel size {self.vessel_size!r}")
        return self

    @property
    def speed(self) -> float:
        """Average speed at sea of the chosen ship size, in knots."""
        value = self.speed_knots.get(self.vessel_size)
        assert value is not None  # checked when the config loads
        return value


class Relevance(BaseModel):
    """What counts as relevant for the focus region's buyer (spec 013)."""

    min_region_share: float = 5.0
    extra_chokepoints: list[str] = []
    event_radius_km: float = 1000.0
    series: list[str] = []


class ScenarioPreset(BaseModel):
    label: str
    closed: list[str]  # chokepoint ids


class ScenarioSettings(BaseModel):
    """Route scenarios (spec 014). Settings: the live-status threshold and the presets."""

    closed_below_pct: float = 50.0
    presets: dict[str, ScenarioPreset] = {}


class SourcingConfig(BaseModel):
    focus_region: str
    passage_chokepoints: dict[str, str]
    signals: Signals
    recent_days: int
    landed_cost: LandedCostSettings
    import_controls: dict[str, ImportControl] = {}
    lead_time: LeadTime
    chokepoint_detours: dict[str, str] = {}
    scenarios: ScenarioSettings = ScenarioSettings()
    relevance: Relevance = Relevance()


def load_sourcing_config(path: Path) -> SourcingConfig:
    with path.open(encoding="utf-8") as f:
        return SourcingConfig.model_validate(yaml.safe_load(f))
