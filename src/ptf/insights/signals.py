"""Traffic lights and the "what changed" list of the situation page.

Each light compares one number with two thresholds from `config/sourcing.yaml`. Higher is
worse in all three cases: rising feedstock prices, more imports through disrupted
chokepoints, more supply-chain pressure.
"""

from dataclasses import dataclass

import pandas as pd

from ptf.insights.config import Signals, Threshold
from ptf.markets import indicators

GREEN, YELLOW, ORANGE, RED = "green", "yellow", "orange", "red"


@dataclass
class Signal:
    title: str
    level: str
    value: str
    note: str
    word: str | None = None  # replaces the level's word, e.g. "Mixed" (spec 018)


def level(value: float | None, threshold: Threshold) -> str:
    """Highest level whose threshold `value` reaches; unknown values count as green."""
    if value is None:
        return GREEN
    if value >= threshold.red:
        return RED
    if value >= threshold.orange:
        return ORANGE
    if value >= threshold.yellow:
        return YELLOW
    return GREEN


def diverges(long: float | None, short: float | None, divergence_pct: float) -> bool:
    """True when the short- and long-period moves point in opposite directions and are at
    least `divergence_pct` percentage points apart (spec 018)."""
    if long is None or short is None:
        return False
    return long * short < 0 and abs(long - short) >= divergence_pct


def price_signal(market_eur: pd.DataFrame, signals: Signals) -> Signal:
    """Change of the feedstock price (in EUR) over the long and the short period.

    The level follows the long period; when the two periods point in opposite directions
    by more than `divergence_pct`, a green light becomes "Mixed" (watch level).
    """
    config = signals.price
    change = indicators.change_pct(market_eur, config.series, config.days)
    short = indicators.change_pct(market_eur, config.series, config.short_days)
    latest = indicators.latest(market_eur, config.series)
    names = market_eur.loc[market_eur["series_id"] == config.series, ["name", "unit"]]
    name, unit = (names.iloc[0]["name"], names.iloc[0]["unit"]) if len(names) else ("", "")
    value = "n/a" if change is None else _pct(change)
    note = f"{name} over {config.days} days; {config.short_days} days: " + (
        "n/a" if short is None else _pct(short)
    )
    if latest is not None:
        note += f" · now {latest[1]:,.1f} {unit} ({latest[0]:%d %b %Y})"
    result = level(change, config)
    word = None
    if diverges(change, short, config.divergence_pct):
        word = "Mixed"
        if result == GREEN:
            result = YELLOW
    return Signal("Price", result, value, note, word)


def _pct(value: float) -> str:
    return f"{value:+.1f} %".replace("-", "\u2212")


def pct_range(low: float, high: float) -> str:
    """'40 %' or '35–40 %' (a range where a country's export port is not known)."""
    if round(low) == round(high):
        return f"{high:.0f} %"
    return f"{low:.0f}–{high:.0f} %"


def supply_signal(
    exposed: tuple[float, float],
    at_risk: tuple[float, float],
    delayed: tuple[float, float],
    extra_t: float,
    year: int,
    scenario_label: str,
    signals: Signals,
) -> Signal:
    """Share of extra-regional imports at risk (behind a closed chokepoint without a sea
    detour) or delayed (on a detour), as ranges (spec 014). The level uses the upper bound of
    the exposed share (at risk or delayed)."""
    note = (
        f"at risk {pct_range(*at_risk)} (no sea detour), on a detour {pct_range(*delayed)}; "
        f"of {extra_t / 1e6:,.1f} Mt imports from outside the region ({year}); "
        f"scenario: {scenario_label}"
    )
    return Signal("Supply", level(exposed[1], signals.supply), pct_range(*exposed), note)


def logistics_signal(market: pd.DataFrame, signals: Signals) -> Signal:
    """Latest Global Supply Chain Pressure Index (standard deviations from the average)."""
    config = signals.logistics
    latest = indicators.latest(market, config.series)
    value = None if latest is None else latest[1]
    text = "n/a" if latest is None else f"{latest[1]:+.2f}"
    note = "supply chain pressure (NY Fed GSCPI), std. dev. from average"
    if latest is not None:
        note += f" · {latest[0]:%b %Y}"
    return Signal("Logistics", level(value, config), text, note)


def newly_disrupted(history: pd.DataFrame, days: int) -> pd.DataFrame:
    """Locations flagged on the latest date but not `days` days earlier (monitor table)."""
    latest_date = history["date"].max()
    now = history[history["date"] == latest_date]
    before = history[history["date"] == latest_date - pd.Timedelta(days=days)]
    was_flagged = set(before.loc[before["is_disrupted"], "location_id"])
    flagged = now[now["is_disrupted"] & ~now["location_id"].isin(was_flagged)]
    return flagged.reset_index(drop=True)


def new_events(events: pd.DataFrame, as_of: pd.Timestamp, days: int) -> pd.DataFrame:
    """Orange and red disruption events that started within `days` before `as_of`."""
    recent = events["from_date"] > as_of - pd.Timedelta(days=days)
    severe = events["alert_level"].isin(["ORANGE", "RED"])
    return events[recent & severe & (events["from_date"] <= as_of)].reset_index(drop=True)


# A comparison value may be a few days older than `days` (weekends, holidays), not more.
MAX_GAP_DAYS = 4


def largest_moves(
    market: pd.DataFrame, days: int = 7, n: int = 3, series_ids: list[str] | None = None
) -> pd.DataFrame:
    """The `n` daily series with the largest absolute change over `days` days, in %.

    Only daily series: a monthly series has no change over a week. The comparison value is
    the last one at least `days` before the newest, but at most `days` + 4 days before it,
    so a sparse series never reports a 30-day move as a 7-day move (spec 013).
    """
    if "frequency" in market.columns:
        market = market[market["frequency"] == "daily"]
    if series_ids is not None:
        market = market[market["series_id"].isin(series_ids)]
    rows = []
    for series_id in market["series_id"].unique():
        one = indicators.series(market, str(series_id))
        newest = one.iloc[-1]
        window = one[
            (one["date"] <= newest["date"] - pd.Timedelta(days=days))
            & (one["date"] >= newest["date"] - pd.Timedelta(days=days + MAX_GAP_DAYS))
        ]
        if window.empty or window.iloc[-1]["value"] == 0:
            continue
        change = float((newest["value"] / window.iloc[-1]["value"] - 1) * 100)
        name = market.loc[market["series_id"] == series_id, "name"].iloc[0]
        rows.append({"series_id": series_id, "name": name, "change_pct": change})
    moves = pd.DataFrame(rows, columns=["series_id", "name", "change_pct"])
    if moves.empty:
        return moves
    return moves.loc[moves["change_pct"].abs().sort_values(ascending=False).index].head(n)
