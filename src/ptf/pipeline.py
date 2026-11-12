"""Command-line entry point for the pipeline: raw -> clean -> report -> model.

    uv run python -m ptf.pipeline ingest   # download/compute raw data (cached)
    uv run python -m ptf.pipeline clean    # build the clean layer
    uv run python -m ptf.pipeline report   # write docs/data_quality.md and charts
    uv run python -m ptf.pipeline model    # model layer, transport LP, docs/model_results.md
    uv run python -m ptf.pipeline portwatch  # chokepoint transits (incremental) -> clean layer
    uv run python -m ptf.pipeline market   # FRED prices and NY Fed GSCPI -> clean layer
    uv run python -m ptf.pipeline all      # all steps

Each step is a plain function, so Airflow (phase 5) can call the same steps as tasks.
"""

import argparse
import logging

import pandas as pd

from ptf.clean import brent as clean_brent
from ptf.clean.comtrade import build_country_lookup, load_raw_comtrade, to_trade_reports
from ptf.clean.dq_report import build_report
from ptf.clean.market import clean_market_series, parse_fred_csv
from ptf.clean.mirror import build_mirror_table
from ptf.clean.portwatch import clean_chokepoints, clean_transits
from ptf.clean.quality import add_unit_values, flag_unit_value_outliers
from ptf.clean.reconcile import reconcile_flows, regional_unit_values
from ptf.config import Settings, get_settings
from ptf.ingest import comtrade, distances, fred, gscpi, portwatch
from ptf.market_config import load_market_config
from ptf.model import inputs as model_inputs
from ptf.model.compare import comparison_metrics, comparison_table
from ptf.model.config import load_model_config
from ptf.model.report import build_model_report
from ptf.model.transport import solve
from ptf.monitor.config import load_monitor_config
from ptf.pipeline_config import PipelineConfig, load_pipeline_config
from ptf.regions import RegionConfig, load_regions

logger = logging.getLogger("ptf.pipeline")


def run_ingest(settings: Settings, regions: RegionConfig, config: PipelineConfig) -> None:
    raw = settings.raw_dir
    # Cheap, unlimited sources first, so a Comtrade quota stop does not block them.
    distances.ingest_distances(regions, raw)
    fred.ingest_fred(raw, [config.brent.fred_series])

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

    daily = parse_fred_csv(fred.latest_raw(raw, config.brent.fred_series))
    daily = daily.rename(columns={"value": "usd_per_bbl"})
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


def run_model(settings: Settings) -> None:
    config = load_model_config(settings.config_dir / "model.yaml")
    year = config.base_year
    flows = pd.read_parquet(settings.clean_dir / "bilateral_flows.parquet")
    distance_table = pd.read_parquet(settings.raw_dir / "distances" / "sea_distances_base.parquet")

    observed = model_inputs.observed_region_flows(flows, year)
    balance = model_inputs.region_balance(observed, config)
    costs = model_inputs.route_costs(distance_table, config)
    folder = model_inputs.write_model_layer(settings.model_dir, year, observed, balance, costs)

    result = solve(model_inputs.build_inputs(balance, costs, config))
    result.flows.to_parquet(folder / "lp_flows.parquet", index=False)
    result.regions.to_parquet(folder / "lp_regions.parquet", index=False)

    region_codes = list(config.regions)
    table = comparison_table(result.flows, observed, region_codes)
    metrics = comparison_metrics(table)
    path = build_model_report(result, table, metrics, region_codes, year, settings.docs_dir)
    logger.info(
        "LP %s: explained share %.0f %%, report %s", year, metrics["explained_share"] * 100, path
    )


def run_portwatch(settings: Settings) -> None:
    """Download new chokepoint days (incremental) and rebuild the clean PortWatch tables."""
    config = load_monitor_config(settings.config_dir / "monitor.yaml")
    raw, clean = settings.raw_dir, settings.clean_dir
    portwatch.ingest_chokepoints(raw)
    portwatch.ingest_chokepoint_transits(raw, revision_days=config.revision_days)
    clean.mkdir(parents=True, exist_ok=True)
    clean_transits(raw).to_parquet(clean / "chokepoint_transits.parquet", index=False)
    clean_chokepoints(raw).to_parquet(clean / "chokepoints.parquet", index=False)


def run_market(settings: Settings) -> None:
    """Refresh stale FRED series and the GSCPI, rebuild `market_series`."""
    config = load_market_config(settings.config_dir / "market_data.yaml")
    raw, clean = settings.raw_dir, settings.clean_dir
    series_ids = [s.id for s in config.fred_series]
    fred.ingest_fred(raw, series_ids, max_age_days=config.max_age_days)
    gscpi.ingest_gscpi(raw, config.gscpi_url, max_age_days=config.max_age_days)
    clean.mkdir(parents=True, exist_ok=True)
    market = clean_market_series(raw, config.fred_series)
    market.to_parquet(clean / "market_series.parquet", index=False)
    logger.info("market data: %s series, %s rows", market["series_id"].nunique(), len(market))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ptf.pipeline", description=__doc__)
    parser.add_argument(
        "step", choices=["ingest", "clean", "report", "model", "portwatch", "market", "all"]
    )
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
    if args.step in ("model", "all"):
        run_model(settings)
    if args.step in ("portwatch", "all"):
        run_portwatch(settings)
    if args.step in ("market", "all"):
        run_market(settings)


if __name__ == "__main__":
    main()
