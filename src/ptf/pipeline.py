"""Command-line entry point for the pipeline: raw -> clean -> report -> model.

    uv run python -m ptf.pipeline ingest   # distances, Brent, BACI trade data (cached)
    uv run python -m ptf.pipeline clean    # BACI -> trade_hs6, bilateral_flows
    uv run python -m ptf.pipeline report   # write docs/data_quality.md and charts
    uv run python -m ptf.pipeline model    # model layer, transport LP, docs/model_results.md
    uv run python -m ptf.pipeline portwatch  # chokepoint transits (incremental) -> clean layer
    uv run python -m ptf.pipeline market   # FRED prices and NY Fed GSCPI -> clean layer
    uv run python -m ptf.pipeline comtrade # superseded own Comtrade download, for comparison
    uv run python -m ptf.pipeline all      # all steps

Each step is a plain function, so Airflow (phase 5) can call the same steps as tasks.
"""

import argparse
import logging

import pandas as pd

from ptf.clean import baci as clean_baci
from ptf.clean import brent as clean_brent
from ptf.clean.comtrade import build_country_lookup, load_raw_comtrade, to_trade_reports
from ptf.clean.dq_report import build_report
from ptf.clean.market import clean_market_series, parse_fred_csv
from ptf.clean.mirror import build_mirror_table
from ptf.clean.portwatch import (
    clean_chokepoints,
    clean_country_trade,
    clean_events,
    clean_port_activity,
    clean_port_links,
    clean_ports,
    clean_transits,
)
from ptf.clean.quality import add_unit_values, flag_unit_value_outliers
from ptf.clean.reconcile import reconcile_flows, regional_unit_values
from ptf.config import Settings, get_settings
from ptf.ingest import baci, comtrade, distances, fred, gscpi, portwatch
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
    """Sea distances, Brent and the BACI trade data (one ~800 MB zip, downloaded once)."""
    raw = settings.raw_dir
    distances.ingest_distances(regions, raw)
    fred.ingest_fred(raw, [config.brent.fred_series])
    baci_config = config.baci
    baci.ingest_baci(raw, baci_config.download_url, baci_config.hs_revision, baci_config.version)


def run_clean(settings: Settings, regions: RegionConfig, config: PipelineConfig) -> None:
    """BACI -> trade_hs6 and bilateral_flows; Brent -> annual averages."""
    raw, clean = settings.raw_dir, settings.clean_dir
    clean.mkdir(parents=True, exist_ok=True)

    baci_config = config.baci
    zip_path = baci.baci_zip_path(raw, baci_config.hs_revision, baci_config.version)
    trade_hs6 = clean_baci.extract_trade_hs6(
        zip_path, baci_config.years, baci_config.hs_prefix, regions.comtrade_aliases
    )
    trade_hs6 = clean_baci.impute_quantities(trade_hs6)
    trade_hs6.to_parquet(clean / "trade_hs6.parquet", index=False)
    flows = clean_baci.to_bilateral_flows(trade_hs6, regions)
    flows.to_parquet(clean / "bilateral_flows.parquet", index=False)

    brent_csv = fred.latest_raw(raw, config.brent.fred_series)
    if brent_csv is None:
        raise FileNotFoundError("no Brent data: run `pipeline ingest` first")
    daily = parse_fred_csv(brent_csv)
    daily = daily.rename(columns={"value": "usd_per_bbl"})
    clean_brent.annual_brent(daily).to_parquet(clean / "brent_annual.parquet", index=False)
    logger.info("clean layer: %s HS6 flows, %s bilateral flows", len(trade_hs6), len(flows))


def run_comtrade(settings: Settings, regions: RegionConfig, config: PipelineConfig) -> None:
    """Superseded by BACI (ADR-009): own Comtrade download and reconciliation, kept as a check.

    Writes trade_reports, mirror and comtrade_flows; the data-quality report compares
    comtrade_flows with BACI where both exist.
    """
    raw = settings.raw_dir
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

    clean_comtrade(settings, regions, config)


def clean_comtrade(settings: Settings, regions: RegionConfig, config: PipelineConfig) -> None:
    """Comtrade raw files -> trade_reports, mirror, comtrade_flows (no download)."""
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
    flows.to_parquet(clean / "comtrade_flows.parquet", index=False)
    logger.info("Comtrade check: %s reports, %s flows", len(reports), len(flows))


def run_report(settings: Settings) -> None:
    path = build_report(settings.clean_dir, settings.docs_dir)
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
    """Download new PortWatch days (incremental) and events, rebuild the clean tables."""
    config = load_monitor_config(settings.config_dir / "monitor.yaml")
    raw, clean = settings.raw_dir, settings.clean_dir
    port_names = {p.id: p.name for p in config.ports}

    portwatch.ingest_chokepoints(raw)
    portwatch.ingest_chokepoint_transits(raw, revision_days=config.revision_days)
    portwatch.ingest_ports_reference(raw, list(port_names))
    portwatch.ingest_port_activity(raw, list(port_names), revision_days=config.revision_days)
    portwatch.ingest_events(raw)
    if config.download_country_trade:
        portwatch.ingest_country_trade(raw, revision_days=config.revision_days)
    portwatch.ingest_port_links(raw, config.min_link_capacity)

    clean.mkdir(parents=True, exist_ok=True)
    clean_transits(raw).to_parquet(clean / "chokepoint_transits.parquet", index=False)
    clean_chokepoints(raw).to_parquet(clean / "chokepoints.parquet", index=False)
    clean_port_activity(raw, port_names).to_parquet(clean / "port_activity.parquet", index=False)
    clean_ports(raw, port_names).to_parquet(clean / "ports.parquet", index=False)
    clean_events(raw).to_parquet(clean / "events.parquet", index=False)
    if any(portwatch.daily_dir(raw, "country_trade_daily").glob("*.parquet")):
        clean_country_trade(raw).to_parquet(clean / "country_trade.parquet", index=False)
    clean_port_links(raw).to_parquet(clean / "port_links.parquet", index=False)


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
        "step",
        choices=["ingest", "clean", "report", "model", "portwatch", "market", "comtrade", "all"],
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
        run_report(settings)
    if args.step in ("model", "all"):
        run_model(settings)
    if args.step in ("portwatch", "all"):
        run_portwatch(settings)
    if args.step in ("market", "all"):
        run_market(settings)
    if args.step == "comtrade":  # superseded by BACI, not part of "all" (ADR-009)
        run_comtrade(settings, regions, config)


if __name__ == "__main__":
    main()
