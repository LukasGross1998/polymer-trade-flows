from pathlib import Path

from ptf.pipeline_config import load_pipeline_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_project_pipeline_config_is_valid() -> None:
    config = load_pipeline_config(REPO_ROOT / "config" / "pipeline.yaml")

    assert config.comtrade.hs_code == "3901"
    assert config.comtrade.years == [2019, 2020, 2021, 2022, 2023, 2024]
    assert config.cleaning.outlier_mad_threshold > 0
