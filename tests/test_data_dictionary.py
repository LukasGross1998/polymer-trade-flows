"""The documentation must list exactly the columns the pipeline writes.

Files in data/ are documented in docs/data_dictionary.md, warehouse tables in the dbt YAML
files (dbt/models/**/_*.yml), which `dbt docs` turns into browsable documentation.
"""

import re

import pandas as pd
import pytest
import yaml
from helpers import (
    REPO_ROOT,
    PipelineSetup,
    write_synthetic_distances,
)

from ptf.core.warehouse import read_table
from ptf.legacy.comtrade import steps as comtrade_steps
from ptf.model import steps as model_steps
from ptf.model.distances import build_distance_table

DICTIONARY = REPO_ROOT / "docs" / "data_dictionary.md"
DBT_MARTS_DIR = REPO_ROOT / "dbt" / "models" / "marts"


def documented_columns(table: str) -> list[str]:
    """Column names from the first cell of each table row in section "## `<table>`"."""
    text = DICTIONARY.read_text(encoding="utf-8")
    section = text.split(f"## `{table}`\n", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    return re.findall(r"^\| `([a-z0-9_]+)` \|", section, flags=re.MULTILINE)


def dbt_documented_columns() -> dict[str, list[str]]:
    """Model name -> documented column names, from all dbt marts YAML files."""
    documented: dict[str, list[str]] = {}
    for path in sorted(DBT_MARTS_DIR.glob("**/_*.yml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        documented.update({m["name"]: [c["name"] for c in m["columns"]] for m in spec["models"]})
    return documented


@pytest.mark.parametrize("model", list(dbt_documented_columns()))
def test_warehouse_marts_match_dbt_docs(warehouse_setup: PipelineSetup, model: str) -> None:
    if model == "mart_country_trade":
        pytest.skip("optional model, disabled while the country trade download is off")
    written = read_table(warehouse_setup.settings, f"marts.{model}")

    assert dbt_documented_columns()[model] == list(written.columns)


@pytest.mark.parametrize("table", ["trade_reports", "mirror", "comtrade_flows"])
def test_comtrade_check_tables_match_dictionary(pipeline_setup: PipelineSetup, table: str) -> None:
    settings = pipeline_setup.settings
    comtrade_steps.clean(settings)

    written = pd.read_parquet(settings.clean_dir / f"{table}.parquet")

    assert documented_columns(table) == list(written.columns)


def test_sea_distances_match_dictionary(pipeline_setup: PipelineSetup) -> None:
    # One region pair is enough to get the column layout; searoute itself is tested elsewhere.
    regions = pipeline_setup.regions.model_copy(
        update={"regions": dict(list(pipeline_setup.regions.regions.items())[:1])}
    )

    assert documented_columns("sea_distances") == list(build_distance_table(regions).columns)


@pytest.mark.parametrize(
    "table",
    ["observed_region_flows", "region_balance", "route_costs", "lp_flows", "lp_regions"],
)
def test_model_tables_match_dictionary(warehouse_setup: PipelineSetup, table: str) -> None:
    settings = warehouse_setup.settings
    write_synthetic_distances(settings.raw_dir, warehouse_setup.regions)
    model_steps.run(settings)

    written = pd.read_parquet(settings.model_dir / "2023" / f"{table}.parquet")

    assert documented_columns(table) == list(written.columns)
