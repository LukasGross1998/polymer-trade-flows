"""docs/data_dictionary.md must list exactly the columns the pipeline writes."""

import json
import re
from pathlib import Path

import pandas as pd
import pytest
from conftest import REPO_ROOT, PipelineSetup, write_synthetic_distances
from test_ingest_comtrade import FakeResponse, FakeSession, no_sleep

from ptf.clean.portwatch import clean_chokepoints, clean_transits
from ptf.ingest import portwatch
from ptf.ingest.distances import build_distance_table
from ptf.pipeline import run_clean, run_model

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


@pytest.mark.parametrize(
    "table",
    ["observed_region_flows", "region_balance", "route_costs", "lp_flows", "lp_regions"],
)
def test_model_tables_match_dictionary(pipeline_setup: PipelineSetup, table: str) -> None:
    settings = pipeline_setup.settings
    run_clean(settings, pipeline_setup.regions, pipeline_setup.config)
    write_synthetic_distances(settings.raw_dir, pipeline_setup.regions)
    run_model(settings)

    written = pd.read_parquet(settings.model_dir / "2023" / f"{table}.parquet")

    assert documented_columns(table) == list(written.columns)


def test_portwatch_tables_match_dictionary(tmp_path: Path) -> None:
    features = json.loads((REPO_ROOT / "tests/fixtures/portwatch_daily_sample.json").read_text())
    session = FakeSession([FakeResponse(200, features)])
    portwatch.ingest_chokepoint_transits(tmp_path, session=session, sleep=no_sleep)
    reference = [{"attributes": {"portid": "c1", "portname": "X", "lat": 1.0, "lon": 2.0}}]
    portwatch.ingest_chokepoints(
        tmp_path, session=FakeSession([FakeResponse(200, {"features": reference})]), sleep=no_sleep
    )

    assert documented_columns("chokepoint_transits") == list(clean_transits(tmp_path).columns)
    assert documented_columns("chokepoints") == list(clean_chokepoints(tmp_path).columns)
