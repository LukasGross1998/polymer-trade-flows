"""End-to-end test of the clean and report steps on fixture data (no network)."""

import json
import shutil
from pathlib import Path

import pandas as pd

from ptf.clean.dq_report import coverage_table
from ptf.config import Settings
from ptf.pipeline import run_clean, run_report
from ptf.pipeline_config import load_pipeline_config
from ptf.regions import load_regions

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


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


def test_clean_and_report_steps(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", docs_dir=tmp_path / "docs")
    write_raw_layer(settings.raw_dir)
    regions = load_regions(REPO_ROOT / "config" / "regions.yaml")
    config = load_pipeline_config(REPO_ROOT / "config" / "pipeline.yaml")

    run_clean(settings, regions, config)
    run_report(settings, regions, config)

    flows = pd.read_parquet(settings.clean_dir / "bilateral_flows.parquet")
    usa_deu = flows[(flows["exporter_iso3"] == "USA") & (flows["importer_iso3"] == "DEU")]
    assert usa_deu["basis"].tolist() == ["import_report"]
    assert usa_deu["qty_gap_pct"].iloc[0] > 0  # importer reports more than exporter

    report = (settings.docs_dir / "data_quality.md").read_text()
    assert "Mirror statistics" in report
    assert (settings.docs_dir / "figures" / "dq_mirror_gaps.png").exists()
    assert (settings.clean_dir / "brent_annual.parquet").exists()


def test_coverage_separates_no_data_from_not_downloaded(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", docs_dir=tmp_path / "docs")
    write_raw_layer(settings.raw_dir)
    pd.DataFrame().to_parquet(settings.raw_dir / "comtrade" / "USA_2024.parquet")  # no data
    regions = load_regions(REPO_ROOT / "config" / "regions.yaml")
    config = load_pipeline_config(REPO_ROOT / "config" / "pipeline.yaml")
    run_clean(settings, regions, config)

    coverage = coverage_table(
        settings.clean_dir / "trade_reports.parquet",
        settings.raw_dir,
        reporters=["DEU", "USA", "CHN"],
        years=[2023, 2024],
    )

    assert coverage.loc["DEU", 2023] == 10  # 12 fixture rows minus the two "World" rows
    assert coverage.loc["USA", 2024] == 0  # asked, but no data
    assert pd.isna(coverage.loc["CHN", 2023])  # never downloaded
