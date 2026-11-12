"""Typed access to `config/monitor.yaml`."""

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


class MonitorConfig(BaseModel):
    baseline_years: list[int]
    rolling_window_days: int = Field(ge=1)
    disruption_threshold: float = Field(gt=0, lt=1)
    min_baseline_per_day: float = Field(ge=0)
    red_sea: RedSeaConfig
    revision_days: int = Field(ge=0)
    ports: list[PortConfig] = []
    min_link_capacity: float = Field(default=1000, ge=0)


def load_monitor_config(path: Path) -> MonitorConfig:
    with path.open(encoding="utf-8") as f:
        return MonitorConfig.model_validate(yaml.safe_load(f))
