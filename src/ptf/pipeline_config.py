"""Typed access to `config/pipeline.yaml` (years, HS code, cleaning thresholds)."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class ComtradeConfig(BaseModel):
    hs_code: str
    years: list[int]
    request_pause_seconds: float
    max_retries: int


class BrentConfig(BaseModel):
    fred_series: str


class CleaningConfig(BaseModel):
    outlier_mad_threshold: float


class PipelineConfig(BaseModel):
    comtrade: ComtradeConfig
    brent: BrentConfig
    cleaning: CleaningConfig


def load_pipeline_config(path: Path) -> PipelineConfig:
    with path.open(encoding="utf-8") as f:
        return PipelineConfig.model_validate(yaml.safe_load(f))
