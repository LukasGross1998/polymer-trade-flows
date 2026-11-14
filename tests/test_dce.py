"""DCE LLDPE price via AKShare (spec 011): AKShare is always replaced by a fake here."""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from ptf.markets import dce, indicators

START = date(2026, 1, 1)
NOW = datetime(2026, 11, 14, tzinfo=UTC)


def akshare_answer(days: list[str], closes: list[float]) -> pd.DataFrame:
    """The shape AKShare's futures_main_sina returns: Chinese column names."""
    return pd.DataFrame(
        {
            "日期": days,
            "开盘价": closes,
            "最高价": closes,
            "最低价": closes,
            "收盘价": closes,
            "成交量": [1000] * len(days),
            "持仓量": [2000] * len(days),
            "动态结算价": closes,
        }
    )


def test_download_with_a_fake_and_landing(tmp_path: Path) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake(symbol: str, start: str, end: str) -> pd.DataFrame:
        calls.append((symbol, start, end))
        return akshare_answer(["2026-11-12", "2026-11-13"], [8368.0, 8578.0])

    path = dce.ingest_dce(tmp_path, "L0", START, fetch=fake, today=NOW)
    landing = pd.read_parquet(dce.write_dce_landing(tmp_path))

    assert path is not None
    assert calls == [("L0", "20260101", "20261114")]
    assert landing["close"].tolist() == [8368.0, 8578.0]
    assert landing["date"].iloc[-1] == pd.Timestamp("2026-11-13")


def test_newest_download_wins_per_day(tmp_path: Path) -> None:
    first = lambda *_: akshare_answer(["2026-11-13"], [8500.0])  # noqa: E731
    revised = lambda *_: akshare_answer(["2026-11-13"], [8578.0])  # noqa: E731
    dce.ingest_dce(tmp_path, "L0", START, fetch=first, today=NOW)
    dce.ingest_dce(tmp_path, "L0", START, fetch=revised, today=datetime(2026, 11, 15, tzinfo=UTC))

    landing = pd.read_parquet(dce.write_dce_landing(tmp_path))

    assert landing["close"].tolist() == [8578.0]


def test_missing_akshare_or_failing_source_does_not_stop_the_step(tmp_path: Path) -> None:
    def missing(*_: str) -> pd.DataFrame:
        raise ImportError("No module named 'akshare'")

    def broken(*_: str) -> pd.DataFrame:
        raise ValueError("Sina changed its page")

    assert dce.ingest_dce(tmp_path, "L0", START, fetch=missing, today=NOW) is None
    assert dce.ingest_dce(tmp_path, "L0", START, fetch=broken, today=NOW) is None
    assert pd.read_parquet(dce.write_dce_landing(tmp_path)).empty  # dbt still builds


def test_cny_to_usd_with_the_same_or_previous_day_rate() -> None:
    prices = pd.DataFrame({"date": pd.to_datetime(["2026-11-13"]), "value": [8000.0]})
    rates = pd.DataFrame({"date": pd.to_datetime(["2026-11-12"]), "value": [7.20]})

    usd = indicators.cny_to_usd(prices, rates)

    assert usd["value"].iloc[0] == pytest.approx(1111.11, abs=0.01)  # 8,000 / 7.20
