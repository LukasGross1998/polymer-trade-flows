"""docs/data_dictionary.md must list exactly the columns the pipeline writes."""

import re

import pandas as pd
import pytest
from conftest import REPO_ROOT, PipelineSetup

from ptf.ingest.distances import build_distance_table
from ptf.pipeline import run_clean

DICTIONARY = REPO_ROOT / "docs" / "data_dictionary.md"


def documented_columns(table: str) -> list[str]:
    """Column names from the first cell of each table row in section "## `<table>`"."""
    text = DICTIONARY.read_text(encoding="utf-8")
    section = text.split(f"## `{table}`\n", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    return re.findall(r"^\| `([a-z0-9_]+)` \|", section, flags=re.MULTILINE)


@pytest.mark.parametrize("table", ["trade_reports", "mirror", "bilateral_flows", "brent_annual"])
def test_clean_tables_match_dictionary(pipeline_setup: PipelineSetup, table: str) -> None:
    settings = pipeline_setup.settings
    run_clean(settings, pipeline_setup.regions, pipeline_setup.config)

    written = pd.read_parquet(settings.clean_dir / f"{table}.parquet")

    assert documented_columns(table) == list(written.columns)


def test_sea_distances_match_dictionary(pipeline_setup: PipelineSetup) -> None:
    # One region pair is enough to get the column layout; searoute itself is tested elsewhere.
    regions = pipeline_setup.regions.model_copy(
        update={"regions": dict(list(pipeline_setup.regions.regions.items())[:1])}
    )

    assert documented_columns("sea_distances") == list(build_distance_table(regions).columns)
