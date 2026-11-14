"""Pipeline steps of the trade domain; each takes only the settings (CLI, later Airflow)."""

import logging

from ptf.core import warehouse
from ptf.core.regions import load_regions
from ptf.core.settings import Settings
from ptf.trade import baci, duties
from ptf.trade.config import load_trade_config
from ptf.trade.quality_report import build_report
from ptf.trade.reference import write_reference_tables

logger = logging.getLogger(__name__)

CONFIG_FILE = "trade.yaml"


def ingest(settings: Settings) -> None:
    """Download the BACI release (one ~800 MB zip, cached) and the EU duties (WITS)."""
    trade = load_trade_config(settings.config_dir / CONFIG_FILE)
    config = trade.baci
    baci.ingest_baci(settings.raw_dir, config.download_url, config.hs_revision, config.version)
    wits = trade.wits
    duties.ingest_duties(settings.raw_dir, wits.reporter, wits.hs6, wits.years_back)


def build(settings: Settings) -> None:
    """BACI landing files and region reference, then `dbt build --select tag:trade`.

    Python only unpacks BACI and writes the configuration as reference tables; all trade
    transformations and their tests run in dbt (dbt/models) into data/warehouse.duckdb.
    """
    raw = settings.raw_dir
    config = load_trade_config(settings.config_dir / CONFIG_FILE).baci
    zip_path = baci.baci_zip_path(raw, config.hs_revision, config.version)
    baci.write_landing(zip_path, config.years, config.hs_prefix, raw)
    duties.write_duty_landing(raw)
    write_reference_tables(load_regions(settings.config_dir / "regions.yaml"), raw)
    warehouse.run_dbt(settings, ["build", "--select", "tag:trade"])
    logger.info("trade marts built in %s", warehouse.warehouse_path(settings))


def report(settings: Settings) -> None:
    """Write docs/data_quality.md and its charts from the trade marts."""
    path = build_report(warehouse.warehouse_path(settings), settings.clean_dir, settings.docs_dir)
    logger.info("report written to %s", path)
