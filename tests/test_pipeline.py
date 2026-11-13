"""End-to-end tests of the clean, report and Comtrade-check steps on fixture data (no network).

The BACI fixture (tests/conftest.py) holds four polyethylene flows and one crude-oil flow:
    USA -> DEU  HDPE 1,000 t for 1.2 m USD, LDPE 1,000 t for 1.3 m USD
    USA -> CHN  HDPE without quantity, 0.6 m USD
    "Other Asia, nes" (Taiwan) -> CHN  LDPE 500 t for 0.65 m USD
    USA -> DEU  crude oil (HS 2709): not polyethylene, must be dropped
"""

import pandas as pd
import pytest
from helpers import PipelineSetup

from ptf.pipeline import clean_comtrade, run_clean, run_report


def flow(flows: pd.DataFrame, exporter: str, importer: str) -> pd.Series:
    match = flows[(flows["exporter_iso3"] == exporter) & (flows["importer_iso3"] == importer)]
    assert len(match) == 1
    return match.iloc[0]


def test_clean_builds_bilateral_flows_from_baci(pipeline_setup: PipelineSetup) -> None:
    settings = pipeline_setup.settings

    run_clean(settings, pipeline_setup.regions, pipeline_setup.config)

    flows = pd.read_parquet(settings.clean_dir / "bilateral_flows.parquet")
    usa_deu = flow(flows, "USA", "DEU")
    assert usa_deu["qty_t"] == pytest.approx(2000)  # HDPE + LDPE, crude oil excluded
    assert usa_deu["value_usd"] == pytest.approx(2_500_000)  # thousand USD -> USD
    assert (usa_deu["exporter_region"], usa_deu["importer_region"]) == ("NAM", "EUR")

    # Missing quantity: 600,000 USD / median HDPE unit value 1,200 USD/t = 500 t, flagged.
    usa_chn = flow(flows, "USA", "CHN")
    assert usa_chn["qty_t"] == pytest.approx(500)
    assert usa_chn["imputed_qty_t"] == pytest.approx(500)

    assert flow(flows, "TWN", "CHN")["exporter_region"] == "NEA"  # S19 alias -> Taiwan
    assert (settings.clean_dir / "brent_annual.parquet").exists()


def test_report_without_and_with_comtrade_check(pipeline_setup: PipelineSetup) -> None:
    settings = pipeline_setup.settings
    regions, config = pipeline_setup.regions, pipeline_setup.config
    run_clean(settings, regions, config)

    run_report(settings)
    report = (settings.docs_dir / "data_quality.md").read_text()
    assert "Traded tonnes by product" in report
    assert "BACI vs. our own Comtrade" not in report  # no Comtrade data yet

    clean_comtrade(settings, regions, config)
    run_report(settings)
    report = (settings.docs_dir / "data_quality.md").read_text()
    assert "BACI vs. our own Comtrade" in report
    assert (settings.docs_dir / "figures" / "dq_baci_vs_comtrade.png").exists()
