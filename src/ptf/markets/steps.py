"""Pipeline step of the markets domain; takes only the settings (CLI, app, later Airflow)."""

from ptf.core import warehouse
from ptf.core.settings import Settings
from ptf.markets import dce, eurostat, fred, gscpi
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
    if config.eurostat_series:
        eurostat.ingest_eurostat(raw, config.eurostat_series)
    eurostat.write_landing(raw)
    download_dce(settings)  # does nothing but write the landing files without AKShare
    write_market_reference(config, raw)
    warehouse.run_dbt(settings, ["build", "--select", "tag:markets"])


def download_dce(settings: Settings) -> None:
    """Dalian LLDPE: daily history and latest quote into the raw layer, plus landing files.

    Needs AKShare (optional extra `asia`, ADR-015); without it only the landing files are
    (re)written, so dbt builds. No dbt run here: in Docker this step runs in the isolated
    `asia` container, which sees only `data/raw/dce` (spec 012); the marts are built by
    `ptf market` in the normal pipeline container.
    """
    config = load_market_config(settings.config_dir / CONFIG_FILE)
    raw = settings.raw_dir
    if config.dce is not None:
        dce.ingest_dce(raw, config.dce.symbol, config.dce.start_date)
        dce.ingest_quote(raw, config.dce.symbol)
    dce.write_dce_landing(raw)
    dce.write_quote_landing(raw)
