"""Shared pytest fixtures. Helpers and fakes used by several test modules: tests/helpers.py."""

from pathlib import Path

import pytest
from helpers import REPO_ROOT, PipelineSetup, write_raw_layer

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
