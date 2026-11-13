"""The superseded Comtrade check (ADR-009) as pipeline steps; only the CLI calls them."""

import logging

import pandas as pd

from ptf.core.regions import load_regions
from ptf.core.settings import Settings
from ptf.legacy.comtrade import ingest
from ptf.legacy.comtrade.clean import build_country_lookup, load_raw_comtrade, to_trade_reports
from ptf.legacy.comtrade.config import load_comtrade_config
from ptf.legacy.comtrade.mirror import build_mirror_table
from ptf.legacy.comtrade.quality import add_unit_values, flag_unit_value_outliers
from ptf.legacy.comtrade.reconcile import reconcile_flows, regional_unit_values

logger = logging.getLogger(__name__)

CONFIG_FILE = "comtrade.yaml"


def run(settings: Settings) -> None:
    """Own Comtrade download and reconciliation, kept as a check against BACI.

    Writes trade_reports, mirror and comtrade_flows; the data-quality report compares
    comtrade_flows with BACI where both exist.
    """
    raw = settings.raw_dir
    regions = load_regions(settings.config_dir / "regions.yaml")
    config = load_comtrade_config(settings.config_dir / CONFIG_FILE).comtrade
    ingest.ingest_reference("partnerAreas", raw)
    reporters_path = ingest.ingest_reference("Reporters", raw)
    reporters = ingest.reporter_codes(pd.read_parquet(reporters_path), regions.reporters())
    ingest.ingest_comtrade(
        reporters,
        config.years,
        config.hs_code,
        raw,
        pause_seconds=config.request_pause_seconds,
        max_retries=config.max_retries,
    )
    clean(settings)


def clean(settings: Settings) -> None:
    """Comtrade raw files -> trade_reports, mirror, comtrade_flows (no download)."""
    raw, clean_dir = settings.raw_dir, settings.clean_dir
    regions = load_regions(settings.config_dir / "regions.yaml")
    config = load_comtrade_config(settings.config_dir / CONFIG_FILE)
    clean_dir.mkdir(parents=True, exist_ok=True)
    partner_areas = pd.read_parquet(raw / "comtrade_reference" / "partnerAreas.parquet")
    lookup = build_country_lookup(partner_areas, regions.comtrade_aliases)
    reports = to_trade_reports(load_raw_comtrade(raw), lookup)
    reports = reports[reports["year"].isin(config.comtrade.years)]
    reports = flag_unit_value_outliers(
        add_unit_values(reports), config.cleaning.outlier_mad_threshold
    )
    reports.to_parquet(clean_dir / "trade_reports.parquet", index=False)
    mirror = build_mirror_table(reports)
    mirror.to_parquet(clean_dir / "mirror.parquet", index=False)
    flows = reconcile_flows(mirror, regional_unit_values(reports, regions), regions)
    flows.to_parquet(clean_dir / "comtrade_flows.parquet", index=False)
    logger.info("Comtrade check: %s reports, %s flows", len(reports), len(flows))
