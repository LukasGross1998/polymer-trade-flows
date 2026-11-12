"""Command-line entry point for the data pipeline: raw -> clean -> report.

    uv run python -m ptf.pipeline ingest   # download/compute raw data (cached)
    uv run python -m ptf.pipeline clean    # build the clean layer
    uv run python -m ptf.pipeline report   # write docs/data_quality.md and charts
    uv run python -m ptf.pipeline all      # all three steps

Each step is a plain function, so Airflow (phase 5) can call the same steps as tasks.
"""

import argparse
import logging

import pandas as pd

from ptf.clean import brent as clean_brent
from ptf.clean.comtrade import build_country_lookup, load_raw_comtrade, to_trade_reports
from ptf.clean.dq_report import build_report
from ptf.clean.mirror import build_mirror_table
from ptf.clean.quality import add_unit_values, flag_unit_value_outliers
from ptf.clean.reconcile import reconcile_flows, regional_unit_values
from ptf.config import Settings, get_settings
from ptf.ingest import brent, comtrade, distances
from ptf.pipeline_config import PipelineConfig, load_pipeline_config
from ptf.regions import RegionConfig, load_regions

logger = logging.getLogger("ptf.pipeline")


def run_ingest(settings: Settings, regions: RegionConfig, config: PipelineConfig) -> None:
    raw = settings.raw_dir
    # Cheap, unlimited sources first, so a Comtrade quota stop does not block them.
    distances.ingest_distances(regions, raw)
    brent.ingest_brent(raw, config.brent.fred_series)

    comtrade.ingest_reference("partnerAreas", raw)
    reporters_path = comtrade.ingest_reference("Reporters", raw)
    reporters = comtrade.reporter_codes(pd.read_parquet(reporters_path), regions.reporters())

    comtrade.ingest_comtrade(
        reporters,
        config.comtrade.years,
        config.comtrade.hs_code,
        raw,
        pause_seconds=config.comtrade.request_pause_seconds,
        max_retries=config.comtrade.max_retries,
    )


def run_clean(settings: Settings, regions: RegionConfig, config: PipelineConfig) -> None:
    raw, clean = settings.raw_dir, settings.clean_dir
    clean.mkdir(parents=True, exist_ok=True)

    partner_areas = pd.read_parquet(raw / "comtrade_reference" / "partnerAreas.parquet")
    lookup = build_country_lookup(partner_areas, regions.comtrade_aliases)
    reports = to_trade_reports(load_raw_comtrade(raw), lookup)
    reports = reports[reports["year"].isin(config.comtrade.years)]
    reports = flag_unit_value_outliers(
        add_unit_values(reports), config.cleaning.outlier_mad_threshold
    )
    reports.to_parquet(clean / "trade_reports.parquet", index=False)

    mirror = build_mirror_table(reports)
    mirror.to_parquet(clean / "mirror.parquet", index=False)

    flows = reconcile_flows(mirror, regional_unit_values(reports, regions), regions)
    flows.to_parquet(clean / "bilateral_flows.parquet", index=False)

    daily = clean_brent.parse_brent_csv(brent.raw_brent_path(raw, config.brent.fred_series))
    clean_brent.annual_brent(daily).to_parquet(clean / "brent_annual.parquet", index=False)
    logger.info("clean layer: %s reports, %s bilateral flows", len(reports), len(flows))


def run_report(settings: Settings, regions: RegionConfig, config: PipelineConfig) -> None:
    reporters_path = settings.raw_dir / "comtrade_reference" / "Reporters.parquet"
    reporters = comtrade.reporter_codes(pd.read_parquet(reporters_path), regions.reporters())
    path = build_report(
        settings.clean_dir,
        settings.docs_dir,
        settings.raw_dir,
        list(reporters),
        config.comtrade.years,
    )
    logger.info("report written to %s", path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ptf.pipeline", description=__doc__)
    parser.add_argument("step", choices=["ingest", "clean", "report", "all"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    regions = load_regions(settings.config_dir / "regions.yaml")
    config = load_pipeline_config(settings.config_dir / "pipeline.yaml")

    if args.step in ("ingest", "all"):
        run_ingest(settings, regions, config)
    if args.step in ("clean", "all"):
        run_clean(settings, regions, config)
    if args.step in ("report", "all"):
        run_report(settings, regions, config)


if __name__ == "__main__":
    main()
