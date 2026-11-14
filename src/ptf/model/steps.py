"""Pipeline steps of the model domain; each takes only the settings (CLI, later Airflow).

The model reads trade data from the warehouse (`marts.mart_region_trade`), not from the
trade package: the warehouse is the interface between domains (ADR-012).
"""

import logging

import pandas as pd

from ptf.core import warehouse
from ptf.core.regions import load_regions
from ptf.core.settings import Settings
from ptf.model import distances
from ptf.model import inputs as model_inputs
from ptf.model.compare import comparison_metrics, comparison_table
from ptf.model.config import load_model_config
from ptf.model.report import build_model_report
from ptf.model.transport import solve

logger = logging.getLogger(__name__)

CONFIG_FILE = "model.yaml"


def ingest(settings: Settings) -> None:
    """Sea distances between the regions' reference ports, base case and route variants."""
    regions = load_regions(settings.config_dir / "regions.yaml")
    config = load_model_config(settings.config_dir / CONFIG_FILE)
    distances.ingest_distances(regions, settings.raw_dir)
    variants = {name: v.restrictions for name, v in config.route_variants.items()}
    distances.ingest_route_variants(regions, settings.raw_dir, variants)


def run(settings: Settings) -> None:
    """Model layer, transport LP and docs/model_results.md for the configured base year."""
    config = load_model_config(settings.config_dir / CONFIG_FILE)
    if not config.enabled:
        # Spec 015: the LP runs only when all its inputs are sourced.
        logger.warning(
            "Transport LP switched off (config/model.yaml enabled: false); inputs without a "
            "source: %s",
            ", ".join(config.missing_inputs()) or "none",
        )
        return
    year = config.base_year
    flows = warehouse.read_table(settings, "marts.mart_region_trade")
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
