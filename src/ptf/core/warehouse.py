"""The DuckDB warehouse built by dbt (ADR-011): running dbt and reading marts.

Each domain writes its own reference tables from the YAML configuration (regions, ports,
market series) as Parquet files into `reference_dir`; dbt reads them as sources like any
other raw data. That keeps assumptions in `config/` while the data model lives in SQL.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

from ptf.core.settings import Settings

logger = logging.getLogger(__name__)


def reference_dir(raw_dir: Path) -> Path:
    return raw_dir / "reference"


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
        str(settings.dbt_project_dir),
        "--profiles-dir",
        str(settings.dbt_project_dir),
    ]
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.error("dbt output:\n%s", result.stdout[-4000:])
        raise RuntimeError(f"dbt {' '.join(args)} failed (exit {result.returncode})")
    logger.info("dbt %s: %s", " ".join(args), result.stdout.strip().splitlines()[-1])


def read_tables(settings: Settings, tables: dict[str, str]) -> dict[str, pd.DataFrame | None]:
    """Read several warehouse tables in one read-only connection; missing tables -> None.

    The connection is closed afterwards, so `dbt build` can write while the app is running.
    `tables` maps a key of the result to a qualified table name, e.g. "marts.dim_port".
    """
    result: dict[str, pd.DataFrame | None] = {}
    with duckdb.connect(str(warehouse_path(settings)), read_only=True) as connection:
        existing = {
            f"{schema}.{name}"
            for schema, name in connection.execute(
                "SELECT table_schema, table_name FROM information_schema.tables"
            ).fetchall()
        }
        for key, table in tables.items():
            result[key] = (
                connection.execute(f"SELECT * FROM {table}").df() if table in existing else None
            )
    return result


def table_exists(settings: Settings, table: str) -> bool:
    """Whether the warehouse file exists and holds `table` (e.g. "marts.dim_port")."""
    path = warehouse_path(settings)
    if not path.exists():
        return False
    schema, name = table.split(".")
    with duckdb.connect(str(path), read_only=True) as connection:
        found = connection.execute(
            "SELECT count(*) FROM information_schema.tables"
            " WHERE table_schema = ? AND table_name = ?",
            [schema, name],
        ).fetchone()
    return found is not None and found[0] > 0


def read_table(settings: Settings, table: str) -> pd.DataFrame:
    """Read one warehouse table (e.g. "marts.mart_region_trade") as a DataFrame, read-only."""
    with duckdb.connect(str(warehouse_path(settings)), read_only=True) as connection:
        return connection.execute(f"SELECT * FROM {table}").df()
