"""Typed access to `config/pipeline.yaml` (years, HS code, cleaning thresholds)."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class BaciConfig(BaseModel):
    version: str
    hs_revision: str
    url: str
    hs_prefix: str
    years: list[int]

    @property
    def download_url(self) -> str:
        return self.url.format(hs_revision=self.hs_revision, version=self.version)


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
    baci: BaciConfig
    comtrade: ComtradeConfig
    brent: BrentConfig
    cleaning: CleaningConfig


def load_pipeline_config(path: Path) -> PipelineConfig:
    with path.open(encoding="utf-8") as f:
        return PipelineConfig.model_validate(yaml.safe_load(f))
