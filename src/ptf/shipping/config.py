"""Typed access to `config/shipping.yaml`."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class RedSeaConfig(BaseModel):
    red_sea_route: str  # PortWatch id of Bab el-Mandeb
    cape_route: str  # PortWatch id of the Cape of Good Hope


class PortConfig(BaseModel):
    id: str  # PortWatch id
    name: str
    role: str


class Threshold(BaseModel):
    amber: float
    red: float


class WeatherConfig(BaseModel):
    past_days: int = Field(default=7, ge=0, le=92)
    forecast_days: int = Field(default=7, ge=1, le=16)
    waves_m: Threshold = Threshold(amber=4.0, red=6.0)
    gusts_kmh: Threshold = Threshold(amber=62.0, red=89.0)


class MonitorConfig(BaseModel):
    baseline_years: list[int]
    rolling_window_days: int = Field(ge=1)
    disruption_threshold: float = Field(gt=0, lt=1)
    min_baseline_per_day: float = Field(ge=0)
    red_sea: RedSeaConfig
    revision_days: int = Field(ge=0)
    ports: list[PortConfig] = []
    min_link_capacity: float = Field(default=1000, ge=0)
    download_country_trade: bool = False
    weather: WeatherConfig = WeatherConfig()


def load_monitor_config(path: Path) -> MonitorConfig:
    with path.open(encoding="utf-8") as f:
        return MonitorConfig.model_validate(yaml.safe_load(f))
