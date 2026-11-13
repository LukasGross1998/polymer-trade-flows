"""Traffic lights and the "what changed" list of the situation page.

Each light compares one number with two thresholds from `config/sourcing.yaml`. Higher is
worse in all three cases: rising feedstock prices, more imports through disrupted
chokepoints, more supply-chain pressure.
"""

from dataclasses import dataclass

import pandas as pd

from ptf.insights.config import Signals, Threshold
from ptf.markets import indicators

GREEN, AMBER, RED = "green", "amber", "red"


@dataclass
class Signal:
    title: str
    level: str
    value: str
    note: str


def level(value: float | None, threshold: Threshold) -> str:
    """'red' from `red`, 'amber' from `amber`, else 'green'; unknown values count as green."""
    if value is None:
        return GREEN
    if value >= threshold.red:
        return RED
    if value >= threshold.amber:
        return AMBER
    return GREEN


def price_signal(market_eur: pd.DataFrame, signals: Signals) -> Signal:
    """Change of the feedstock price (in EUR) over the configured number of days."""
    config = signals.price
    change = indicators.change_pct(market_eur, config.series, config.days)
    latest = indicators.latest(market_eur, config.series)
    names = market_eur.loc[market_eur["series_id"] == config.series, ["name", "unit"]]
    name, unit = (names.iloc[0]["name"], names.iloc[0]["unit"]) if len(names) else ("", "")
    value = "n/a" if change is None else f"{change:+.1f} %"
    note = f"{name} over {config.days} days"
    if latest is not None:
        note += f" · now {latest[1]:,.1f} {unit} ({latest[0]:%d %b %Y})"
    return Signal("Price", level(change, config), value, note)


def supply_signal(share_pct: float, extra_t: float, year: int, signals: Signals) -> Signal:
    """Share of extra-regional imports whose route passes a disrupted chokepoint."""
    note = (
        f"of {extra_t / 1e6:,.1f} Mt imports from outside the region ({year}) "
        "pass a disrupted chokepoint"
    )
    return Signal("Supply", level(share_pct, signals.supply), f"{share_pct:.0f} %", note)


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


def largest_moves(market: pd.DataFrame, days: int = 30, n: int = 3) -> pd.DataFrame:
    """The `n` market series with the largest absolute change over `days` days, in %."""
    rows = []
    for series_id in market["series_id"].unique():
        change = indicators.change_pct(market, str(series_id), days)
        if change is not None:
            name = market.loc[market["series_id"] == series_id, "name"].iloc[0]
            rows.append({"series_id": series_id, "name": name, "change_pct": change})
    moves = pd.DataFrame(rows, columns=["series_id", "name", "change_pct"])
    if moves.empty:
        return moves
    return moves.loc[moves["change_pct"].abs().sort_values(ascending=False).index].head(n)
