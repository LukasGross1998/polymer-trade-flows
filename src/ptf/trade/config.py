"""Typed access to `config/trade.yaml` (the BACI release, product and years)."""

from datetime import date
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


class EuMembers(BaseModel):
    """The EU's 27 member states (ISO2; Greece also as Eurostat's "EL"), with the source."""

    iso2: list[str]
    source: str
    url: str
    read: date


class ComextConfig(BaseModel):
    """Monthly EU imports from Eurostat Comext (spec 019)."""

    enabled: bool = True
    hs6: list[str] = []
    years_back: int = 2  # setting: from January of the year before last
    eu_members: EuMembers | None = None


class TradeConfig(BaseModel):
    baci: BaciConfig
    wits: WitsConfig = WitsConfig()
    comext: ComextConfig = ComextConfig()


def load_trade_config(path: Path) -> TradeConfig:
    with path.open(encoding="utf-8") as f:
        return TradeConfig.model_validate(yaml.safe_load(f))
