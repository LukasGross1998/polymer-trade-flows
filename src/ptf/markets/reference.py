"""Market reference table for dbt: metadata of the configured series."""

from pathlib import Path

import pandas as pd

from ptf.core.warehouse import reference_dir
from ptf.markets.config import MarketConfig


def write_market_reference(config: MarketConfig, raw_dir: Path) -> Path:
    """Metadata of the market series (name, unit, frequency, group), GSCPI included."""
    rows = [s.model_dump() for s in config.fred_series]
    rows.append(
        {
            "id": "GSCPI",
            "name": "Global Supply Chain Pressure Index (NY Fed)",
            "unit": "std. dev. from average",
            "frequency": "monthly",
            "group": "supply_chain",
        }
    )
    if config.dce is not None:
        rows.append(
            {
                "id": config.dce.series_id,
                "name": config.dce.name,
                "unit": config.dce.unit,
                "frequency": "daily",
                "group": "china_futures",
            }
        )
    path = reference_dir(raw_dir) / "market_series.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).rename(columns={"id": "series_id"}).to_parquet(path, index=False)
    return path
