"""Shared pytest fixtures: a small raw layer built from the recorded API fixtures."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from ptf.config import Settings
from ptf.pipeline_config import PipelineConfig, load_pipeline_config
from ptf.regions import RegionConfig, load_regions

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class PipelineSetup:
    settings: Settings
    regions: RegionConfig
    config: PipelineConfig


def write_raw_layer(raw_dir: Path) -> None:
    """Germany's real 2023 records plus one made-up US export report to Germany."""
    deu = pd.DataFrame(json.loads((FIXTURES / "comtrade_deu_2023.json").read_text())["data"])
    usa = deu[(deu["flowCode"] == "M") & (deu["partnerCode"] == 842)].copy()
    usa = usa.assign(reporterCode=842, partnerCode=276, flowCode="X")
    usa["netWgt"] = usa["netWgt"] * 0.9  # the US reports 10 % less than Germany receives

    (raw_dir / "comtrade").mkdir(parents=True)
    deu.to_parquet(raw_dir / "comtrade" / "DEU_2023.parquet")
    usa.to_parquet(raw_dir / "comtrade" / "USA_2023.parquet")

    areas = json.loads((FIXTURES / "partner_areas.json").read_text())["results"]
    (raw_dir / "comtrade_reference").mkdir()
    pd.DataFrame(areas).to_parquet(raw_dir / "comtrade_reference" / "partnerAreas.parquet")
    reporters = json.loads((FIXTURES / "reporters.json").read_text())["results"]
    pd.DataFrame(reporters).to_parquet(raw_dir / "comtrade_reference" / "Reporters.parquet")

    (raw_dir / "brent").mkdir()
    shutil.copy(FIXTURES / "brent_sample.csv", raw_dir / "brent" / "DCOILBRENTEU.csv")


def write_synthetic_distances(raw_dir: Path, regions: RegionConfig) -> None:
    """5,000 nm between all regions: keeps model tests fast and independent of searoute."""
    rows = [
        {
            "origin_region": o,
            "dest_region": d,
            "origin_port": regions.regions[o].port.name,
            "dest_port": regions.regions[d].port.name,
            "distance_nm": 0.0 if o == d else 5000.0,
        }
        for o in regions.regions
        for d in regions.regions
    ]
    (raw_dir / "distances").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(raw_dir / "distances" / "sea_distances_base.parquet")


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
