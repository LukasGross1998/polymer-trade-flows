"""Typed access to `config/sourcing.yaml` (focus region, chokepoint mapping, thresholds)."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class Threshold(BaseModel):
    """A traffic light: amber from `amber`, red from `red` (both inclusive)."""

    amber: float
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


class SourcingConfig(BaseModel):
    focus_region: str
    passage_chokepoints: dict[str, str]
    signals: Signals
    recent_days: int


def load_sourcing_config(path: Path) -> SourcingConfig:
    with path.open(encoding="utf-8") as f:
        return SourcingConfig.model_validate(yaml.safe_load(f))
