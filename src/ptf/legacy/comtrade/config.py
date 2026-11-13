"""Typed access to `config/comtrade.yaml` (years, HS code, cleaning thresholds)."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class ComtradeConfig(BaseModel):
    hs_code: str
    years: list[int]
    request_pause_seconds: float
    max_retries: int


class CleaningConfig(BaseModel):
    outlier_mad_threshold: float


class ComtradeCheckConfig(BaseModel):
    comtrade: ComtradeConfig
    cleaning: CleaningConfig


def load_comtrade_config(path: Path) -> ComtradeCheckConfig:
    with path.open(encoding="utf-8") as f:
        return ComtradeCheckConfig.model_validate(yaml.safe_load(f))
