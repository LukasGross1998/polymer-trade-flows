"""Typed access to `config/trade.yaml` (the BACI release, product and years)."""

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


class WitsConfig(BaseModel):
    reporter: str = "918"  # European Union
    hs6: list[str] = []
    years_back: int = 6


class TradeConfig(BaseModel):
    baci: BaciConfig
    wits: WitsConfig = WitsConfig()


def load_trade_config(path: Path) -> TradeConfig:
    with path.open(encoding="utf-8") as f:
        return TradeConfig.model_validate(yaml.safe_load(f))
