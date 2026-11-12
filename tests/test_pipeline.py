"""End-to-end test of the clean and report steps on fixture data (no network)."""

import pandas as pd
from conftest import PipelineSetup

from ptf.clean.dq_report import coverage_table
from ptf.pipeline import run_clean, run_report


def test_clean_and_report_steps(pipeline_setup: PipelineSetup) -> None:
    settings = pipeline_setup.settings

    run_clean(settings, pipeline_setup.regions, pipeline_setup.config)
    run_report(settings, pipeline_setup.regions, pipeline_setup.config)

    flows = pd.read_parquet(settings.clean_dir / "bilateral_flows.parquet")
    usa_deu = flows[(flows["exporter_iso3"] == "USA") & (flows["importer_iso3"] == "DEU")]
    assert usa_deu["basis"].tolist() == ["import_report"]
    assert usa_deu["qty_gap_pct"].iloc[0] > 0  # importer reports more than exporter

    report = (settings.docs_dir / "data_quality.md").read_text()
    assert "Mirror statistics" in report
    assert (settings.docs_dir / "figures" / "dq_mirror_gaps.png").exists()
    assert (settings.clean_dir / "brent_annual.parquet").exists()


def test_coverage_separates_no_data_from_not_downloaded(pipeline_setup: PipelineSetup) -> None:
    settings = pipeline_setup.settings
    pd.DataFrame().to_parquet(settings.raw_dir / "comtrade" / "USA_2024.parquet")  # no data
    run_clean(settings, pipeline_setup.regions, pipeline_setup.config)

    coverage = coverage_table(
        settings.clean_dir / "trade_reports.parquet",
        settings.raw_dir,
        reporters=["DEU", "USA", "CHN"],
        years=[2023, 2024],
    )

    assert coverage.loc["DEU", 2023] == 10  # 12 fixture rows minus the two "World" rows
    assert coverage.loc["USA", 2024] == 0  # asked, but no data
    assert pd.isna(coverage.loc["CHN", 2023])  # never downloaded
