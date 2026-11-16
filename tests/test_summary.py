"""Situation page (spec 018): summary sentence, price divergence, buyer notes."""

import pandas as pd
import pytest
from helpers import REPO_ROOT

from ptf.insights import signals, summary
from ptf.insights.config import load_sourcing_config

CONFIG = load_sourcing_config(REPO_ROOT / "config" / "sourcing.yaml")
AS_OF = pd.Timestamp("2026-11-08")


def lights(supply: str, price: str = signals.GREEN, word: str | None = None) -> list:
    return [
        signals.Signal("Price", price, "", "", word),
        signals.Signal("Supply", supply, "", ""),
        signals.Signal("Logistics", signals.ORANGE, "", ""),
    ]


@pytest.mark.parametrize(
    ("level", "at_risk", "delayed", "behind", "expected"),
    [
        (
            signals.RED,
            (16.0, 39.0),
            (12.0, 12.0),
            ["Hormuz"],
            "Supply critical: 16–39 % of extra-European PE imports at risk behind Hormuz, "
            "12 % on a detour",
        ),
        (
            signals.ORANGE,
            (0.0, 0.0),
            (27.0, 51.0),
            [],
            "Supply elevated: 27–51 % on a detour",
        ),
        (
            signals.YELLOW,
            (12.0, 12.0),
            (0.0, 0.0),
            [],
            "Supply watch: 12 % of extra-European PE imports at risk",
        ),
        (
            signals.GREEN,
            (0.0, 0.0),
            (0.0, 0.0),
            [],
            "Supply OK: no extra-European PE imports pass a closed chokepoint",
        ),
    ],
)
def test_summary_sentence_for_every_supply_level(
    level: str,
    at_risk: tuple[float, float],
    delayed: tuple[float, float],
    behind: list[str],
    expected: str,
) -> None:
    text = summary.sentence(lights(level), at_risk, delayed, behind, "Live status", AS_OF)

    assert text.startswith(expected)
    assert text.endswith(
        "; price OK; logistics elevated (live status, chokepoints to 08 Nov 2026)."
    )


def test_mixed_price_word_in_the_sentence() -> None:
    mixed = lights(signals.RED, signals.YELLOW, "Mixed")
    assert "; price mixed;" in summary.sentence(mixed, (0, 0), (0, 0), [], "Live status", AS_OF)


def market(values: list[float]) -> pd.DataFrame:
    dates = pd.to_datetime(["2026-08-10", "2026-10-10", "2026-11-09"])
    return pd.DataFrame(
        {
            "date": dates,
            "series_id": "DCOILBRENTEU",
            "name": "Brent",
            "unit": "EUR/bbl",
            "value": values,
        }
    )


def test_price_card_shows_mixed_when_periods_diverge() -> None:
    # 90 days: 80 -> 83 (+3.75 %); 30 days: 100 -> 83 (-17 %): opposite, 20.75 points apart.
    mixed = signals.price_signal(market([80.0, 100.0, 83.0]), CONFIG.signals)
    assert mixed.word == "Mixed" and mixed.level == signals.YELLOW
    assert "30 days" in mixed.note

    # Same direction: no "Mixed".
    same = signals.price_signal(market([80.0, 81.0, 83.0]), CONFIG.signals)
    assert same.word is None and same.level == signals.GREEN


def test_divergence_rule() -> None:
    assert signals.diverges(3.5, -29.0, 10)
    assert not signals.diverges(3.5, -5.0, 10)  # 8.5 points apart
    assert not signals.diverges(12.0, 2.0, 10)  # same direction
    assert not signals.diverges(None, -29.0, 10)


def test_buyer_notes_by_kind_and_direction() -> None:
    assert summary.market_note("DCOILBRENTEU", "energy", -29.0).startswith("feedstock cost down")
    assert summary.market_note("DEXUSEU", "fx", 2.0).startswith("euro stronger")
    assert summary.market_note("DCE_LLDPE", "china_futures", 3.0).startswith("Asian PE price up")
    assert summary.market_note("GSCPI", "supply_chain", 1.0) == ""


def test_sentence_without_trade_data() -> None:
    text = summary.sentence(lights(signals.GREEN), None, (0, 0), [], "Live status", AS_OF)
    assert text.startswith("Supply: no trade data loaded; price OK")
