"""Typed access to `config/market_data.yaml`."""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SeriesConfig(BaseModel):
    id: str
    name: str
    unit: str
    frequency: str
    group: str


class KeyEvent(BaseModel):
    date: date
    label: str
    source: str


class MarketConfig(BaseModel):
    max_age_days: float = Field(gt=0)
    fred_series: list[SeriesConfig]
    gscpi_url: str
    key_events: list[KeyEvent]


def load_market_config(path: Path) -> MarketConfig:
    with path.open(encoding="utf-8") as f:
        return MarketConfig.model_validate(yaml.safe_load(f))
