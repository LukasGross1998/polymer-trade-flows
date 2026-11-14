"""Pipeline step of the markets domain; takes only the settings (CLI, app, later Airflow)."""

from ptf.core import warehouse
from ptf.core.settings import Settings
from ptf.markets import dce, fred, gscpi
from ptf.markets.config import load_market_config
from ptf.markets.reference import write_market_reference

CONFIG_FILE = "markets.yaml"


def refresh(settings: Settings) -> None:
    """Refresh FRED, the GSCPI and (optional) the DCE price, then `dbt build -s tag:markets`."""
    config = load_market_config(settings.config_dir / CONFIG_FILE)
    raw = settings.raw_dir
    series_ids = [s.id for s in config.fred_series]
    fred.ingest_fred(raw, series_ids, max_age_days=config.max_age_days)
    gscpi.ingest_gscpi(raw, config.gscpi_url, max_age_days=config.max_age_days)
    gscpi.write_gscpi_landing(raw)
    if config.dce is not None:  # optional: needs `uv sync --extra asia` (spec 011)
        dce.ingest_dce(raw, config.dce.symbol, config.dce.start_date)
    dce.write_dce_landing(raw)
    write_market_reference(config, raw)
    warehouse.run_dbt(settings, ["build", "--select", "tag:markets"])
