"""Shared pytest fixtures. Helpers and fakes used by several test modules: tests/helpers.py."""

from pathlib import Path

import pytest
from helpers import REPO_ROOT, PipelineSetup, build_warehouse, write_raw_layer

from ptf.config import Settings
from ptf.pipeline_config import load_pipeline_config
from ptf.regions import load_regions


@pytest.fixture
def pipeline_setup(tmp_path: Path) -> PipelineSetup:
    """Settings pointing at a temporary data lake whose raw layer is already filled."""
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        config_dir=REPO_ROOT / "config",
    )
    write_raw_layer(settings.raw_dir)
    return PipelineSetup(
        settings=settings,
        regions=load_regions(REPO_ROOT / "config" / "regions.yaml"),
        config=load_pipeline_config(REPO_ROOT / "config" / "pipeline.yaml"),
    )


@pytest.fixture(scope="session")
def warehouse_setup(tmp_path_factory: pytest.TempPathFactory) -> PipelineSetup:
    """The fixture raw layer with the full warehouse built by dbt (once per test run).

    `dbt build` takes a few seconds, so tests that read the marts share this one. Tests may
    add deterministic outputs (model layer, synthetic distances) but must not change the raw
    or warehouse data; tests that need their own warehouse use `pipeline_setup`.
    """
    root = tmp_path_factory.mktemp("warehouse")
    settings = Settings(
        _env_file=None,
        data_dir=root / "data",
        docs_dir=root / "docs",
        config_dir=REPO_ROOT / "config",
    )
    write_raw_layer(settings.raw_dir)
    setup = PipelineSetup(
        settings=settings,
        regions=load_regions(REPO_ROOT / "config" / "regions.yaml"),
        config=load_pipeline_config(REPO_ROOT / "config" / "pipeline.yaml"),
    )
    build_warehouse(setup)
    return setup
