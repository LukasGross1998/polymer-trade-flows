"""The DuckDB warehouse built by dbt (ADR-011): reference tables, dbt runs, reading marts.

Python writes the reference tables from the YAML configuration (regions, countries) as
Parquet files in the raw layer; dbt reads them as sources like any other raw data. That
keeps assumptions in `config/` while the data model lives in SQL.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

from ptf.config import Settings
from ptf.regions import RegionConfig

logger = logging.getLogger(__name__)

DBT_PROJECT_DIR = Path(__file__).resolve().parents[2] / "dbt"


def reference_dir(raw_dir: Path) -> Path:
    return raw_dir / "reference"


def write_reference_tables(regions: RegionConfig, raw_dir: Path) -> list[Path]:
    """Regions, country -> region mapping and Comtrade/BACI code aliases as Parquet."""
    folder = reference_dir(raw_dir)
    folder.mkdir(parents=True, exist_ok=True)
    region_rows = [
        {
            "region": code,
            "region_name": region.name,
            "port": region.port.name,
            "port_lon": region.port.lon,
            "port_lat": region.port.lat,
        }
        for code, region in regions.regions.items()
    ]
    country_rows = [
        {"iso3": iso3, "region": code, "is_reporter": iso3 in region.reporters}
        for code, region in regions.regions.items()
        for iso3 in region.countries()
    ]
    alias_rows = [{"code": code, "iso3": iso3} for code, iso3 in regions.comtrade_aliases.items()]
    paths = [
        folder / "regions.parquet",
        folder / "country_region.parquet",
        folder / "country_aliases.parquet",
    ]
    pd.DataFrame(region_rows).to_parquet(paths[0], index=False)
    pd.DataFrame(country_rows).to_parquet(paths[1], index=False)
    pd.DataFrame(alias_rows, columns=["code", "iso3"]).to_parquet(paths[2], index=False)
    return paths


def warehouse_path(settings: Settings) -> Path:
    return settings.data_dir / "warehouse.duckdb"


def run_dbt(settings: Settings, args: list[str]) -> None:
    """Run a dbt command (e.g. ["build"]) on this project's warehouse; raise on failure.

    dbt runs as a separate process: the DuckDB connection it opens is closed when it ends,
    so this process can read the warehouse afterwards. Paths reach dbt as environment
    variables (read by `dbt/profiles.yml` and the sources), the same way the CLI, the tests
    and later Airflow call it.
    """
    warehouse_path(settings).parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PTF_WAREHOUSE": str(warehouse_path(settings).resolve()),
        "PTF_RAW_DIR": str(settings.raw_dir.resolve()),
    }
    dbt = Path(sys.executable).with_name("dbt")  # the dbt installed in this environment
    command = [
        str(dbt),
        *args,
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROJECT_DIR),
    ]
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.error("dbt output:\n%s", result.stdout[-4000:])
        raise RuntimeError(f"dbt {' '.join(args)} failed (exit {result.returncode})")
    logger.info("dbt %s: %s", " ".join(args), result.stdout.strip().splitlines()[-1])


def read_table(settings: Settings, table: str) -> pd.DataFrame:
    """Read one warehouse table (e.g. "marts.mart_region_trade") as a DataFrame, read-only."""
    with duckdb.connect(str(warehouse_path(settings)), read_only=True) as connection:
        return connection.execute(f"SELECT * FROM {table}").df()
