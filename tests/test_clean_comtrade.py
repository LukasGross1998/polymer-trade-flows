import json
from pathlib import Path

import pandas as pd
import pytest

from ptf.legacy.comtrade.clean import TRADE_REPORT_COLUMNS, build_country_lookup, to_trade_reports

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def lookup() -> pd.DataFrame:
    areas = pd.DataFrame(json.loads((FIXTURES / "partner_areas.json").read_text())["results"])
    return build_country_lookup(areas, aliases={"S19": "TWN"})


@pytest.fixture
def raw() -> pd.DataFrame:
    return pd.DataFrame(json.loads((FIXTURES / "comtrade_deu_2023.json").read_text())["data"])


def test_reports_follow_clean_schema(raw: pd.DataFrame, lookup: pd.DataFrame) -> None:
    reports = to_trade_reports(raw, lookup)

    assert list(reports.columns) == TRADE_REPORT_COLUMNS
    assert set(reports["flow"]) == {"import", "export"}
    assert (reports["reporter_iso3"] == "DEU").all()
    assert not reports["is_imputed"].any()


def test_world_partner_is_removed(raw: pd.DataFrame, lookup: pd.DataFrame) -> None:
    reports = to_trade_reports(raw, lookup)

    assert "W00" not in set(reports["partner_iso3"])
    assert len(reports) == 10  # 12 fixture rows minus import and export to "World"


def test_other_asia_nes_is_mapped_to_taiwan(raw: pd.DataFrame, lookup: pd.DataFrame) -> None:
    reports = to_trade_reports(raw, lookup)

    assert "TWN" in set(reports["partner_iso3"])


def test_weight_is_converted_from_kg_to_tonnes(raw: pd.DataFrame, lookup: pd.DataFrame) -> None:
    reports = to_trade_reports(raw, lookup)
    row = reports[(reports["flow"] == "import") & (reports["partner_iso3"] == "USA")].iloc[0]
    raw_row = raw[(raw["flowCode"] == "M") & (raw["partnerCode"] == 842)].iloc[0]

    assert row["qty_t"] == pytest.approx(raw_row["netWgt"] / 1000)
    assert row["value_usd"] == pytest.approx(raw_row["primaryValue"])


def test_zero_or_missing_weight_becomes_nan(raw: pd.DataFrame, lookup: pd.DataFrame) -> None:
    raw = raw.copy()
    raw.loc[raw["partnerCode"] == 842, "netWgt"] = 0.0
    raw.loc[raw["partnerCode"] == 156, "netWgt"] = None

    reports = to_trade_reports(raw, lookup)

    affected = reports["partner_iso3"].isin(["USA", "CHN"])
    assert reports.loc[affected, "qty_t"].isna().all()
    assert reports.loc[~affected, "qty_t"].notna().all()


def test_reexports_are_excluded(raw: pd.DataFrame, lookup: pd.DataFrame) -> None:
    reexport = raw.iloc[[0]].assign(flowCode="RX", partnerCode=842)

    reports = to_trade_reports(pd.concat([raw, reexport]), lookup)

    assert len(reports) == 10


def test_duplicate_reports_are_rejected(raw: pd.DataFrame, lookup: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        to_trade_reports(pd.concat([raw, raw]), lookup)
