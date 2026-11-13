"""The documentation must list exactly the columns the pipeline writes.

Files in data/ are documented in docs/data_dictionary.md, warehouse tables in the dbt YAML
files (dbt/models/**/_*.yml), which `dbt docs` turns into browsable documentation.
"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml
from helpers import (
    REPO_ROOT,
    FakeResponse,
    FakeSession,
    PipelineSetup,
    no_sleep,
    write_synthetic_distances,
)

from ptf.clean.market import MARKET_COLUMNS
from ptf.clean.portwatch import (
    COUNTRY_TRADE_COLUMNS,
    PORT_LINK_COLUMNS,
    clean_chokepoints,
    clean_events,
    clean_port_activity,
    clean_ports,
    clean_transits,
)
from ptf.ingest import portwatch
from ptf.ingest.distances import build_distance_table
from ptf.pipeline import clean_comtrade, run_model
from ptf.warehouse import read_table

DICTIONARY = REPO_ROOT / "docs" / "data_dictionary.md"
DBT_MARTS_YAML = REPO_ROOT / "dbt" / "models" / "marts" / "_marts.yml"


def documented_columns(table: str) -> list[str]:
    """Column names from the first cell of each table row in section "## `<table>`"."""
    text = DICTIONARY.read_text(encoding="utf-8")
    section = text.split(f"## `{table}`\n", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    return re.findall(r"^\| `([a-z0-9_]+)` \|", section, flags=re.MULTILINE)


def dbt_documented_columns() -> dict[str, list[str]]:
    """Model name -> documented column names, from the dbt marts YAML."""
    spec = yaml.safe_load((DBT_MARTS_YAML).read_text(encoding="utf-8"))
    return {m["name"]: [c["name"] for c in m["columns"]] for m in spec["models"]}


def test_brent_annual_matches_dictionary(warehouse_setup: PipelineSetup) -> None:
    written = pd.read_parquet(warehouse_setup.settings.clean_dir / "brent_annual.parquet")

    assert documented_columns("brent_annual") == list(written.columns)


@pytest.mark.parametrize("model", list(dbt_documented_columns()))
def test_warehouse_marts_match_dbt_docs(warehouse_setup: PipelineSetup, model: str) -> None:
    written = read_table(warehouse_setup.settings, f"marts.{model}")

    assert dbt_documented_columns()[model] == list(written.columns)


@pytest.mark.parametrize("table", ["trade_reports", "mirror", "comtrade_flows"])
def test_comtrade_check_tables_match_dictionary(pipeline_setup: PipelineSetup, table: str) -> None:
    settings = pipeline_setup.settings
    clean_comtrade(settings, pipeline_setup.regions, pipeline_setup.config)

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


def test_port_event_and_market_tables_match_dictionary(tmp_path: Path) -> None:
    port_row = {"date": "2026-11-06", "portid": "port24", "portname": "Jubail", "portcalls": 1}
    for column in ["portcalls_tanker", "portcalls_container", "import", "export"]:
        port_row[column] = 0
    portwatch.ingest_port_activity(
        tmp_path,
        ["port24"],
        session=FakeSession([FakeResponse(200, {"features": [{"attributes": port_row}]})]),
        sleep=no_sleep,
    )
    reference = {
        "portid": "port24",
        "portname": "Jubail",
        "country": "SA",
        "lat": 27.0,
        "lon": 49.7,
    }
    portwatch.ingest_ports_reference(
        tmp_path,
        ["port24"],
        session=FakeSession([FakeResponse(200, {"features": [{"attributes": reference}]})]),
        sleep=no_sleep,
    )
    event = {c: None for c in ["eventid", "eventtype", "eventname", "alertlevel", "country"]}
    event.update(fromdate=1772323200000, todate=None, lat=1.0, long=2.0)
    event.update(affectedports="", n_affectedports=0, htmldescription="")
    portwatch.ingest_events(
        tmp_path,
        session=FakeSession([FakeResponse(200, {"features": [{"attributes": event}]})]),
        sleep=no_sleep,
    )
    names = {"port24": "Jubail"}

    assert documented_columns("port_activity") == list(clean_port_activity(tmp_path, names).columns)
    assert documented_columns("ports") == list(clean_ports(tmp_path, names).columns)
    assert documented_columns("events") == list(clean_events(tmp_path).columns)
    assert documented_columns("market_series") == MARKET_COLUMNS


def test_flow_tables_match_dictionary() -> None:
    assert documented_columns("port_links") == PORT_LINK_COLUMNS
    assert documented_columns("country_trade") == COUNTRY_TRADE_COLUMNS
