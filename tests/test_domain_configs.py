"""Each domain reads its own file in config/; the project's files must be valid."""

from pathlib import Path

from ptf.legacy.comtrade.config import load_comtrade_config
from ptf.trade.config import load_trade_config

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_trade_config_is_valid() -> None:
    baci = load_trade_config(CONFIG / "trade.yaml").baci

    assert baci.hs_prefix == "3901"
    assert baci.download_url.endswith("BACI_HS17_V202601.zip")


def test_comtrade_check_config_is_valid() -> None:
    config = load_comtrade_config(CONFIG / "comtrade.yaml")

    assert config.comtrade.hs_code == "3901"
    assert config.comtrade.years == [2019, 2020, 2021, 2022, 2023, 2024]
    assert config.cleaning.outlier_mad_threshold > 0
