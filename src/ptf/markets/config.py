"""Typed access to `config/markets.yaml`."""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ptf.core.sourced import Sourced


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


class DceConfig(BaseModel):
    """Daily futures price from the Dalian Commodity Exchange via AKShare (spec 011)."""

    series_id: str
    symbol: str
    name: str
    unit: str
    start_date: date
    day_close_hour: Sourced | None = None  # close of the day session, Beijing time (spec 018)


class EurostatSeries(BaseModel):
    """One monthly Eurostat series: a dataset with fixed filters (spec 019)."""

    id: str
    dataset: str
    filters: dict[str, str]
    name: str
    unit: str
    since: str = "2019-01"
    frequency: str = "monthly"
    group: str = "eu_prices"


class MarketConfig(BaseModel):
    max_age_days: float = Field(gt=0)
    fred_series: list[SeriesConfig]
    gscpi_url: str
    key_events: list[KeyEvent]
    dce: DceConfig | None = None
    crude_barrels_per_tonne: Sourced | None = None  # for the polymer-over-crude spread
    eurostat_series: list[EurostatSeries] = []


def load_market_config(path: Path) -> MarketConfig:
    with path.open(encoding="utf-8") as f:
        return MarketConfig.model_validate(yaml.safe_load(f))
