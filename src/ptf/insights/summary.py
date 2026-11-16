"""The summary sentence on top of the situation page (spec 018).

Built only from the lights and the scenario – no new numbers, no forecasts:
"Supply critical: 16–39 % of extra-European PE imports at risk behind Hormuz, 12 % on a
detour; price OK; logistics elevated (live status, chokepoints to 08 Nov 2026)."
"""

import pandas as pd

from ptf.insights import signals

WORDS = {
    signals.GREEN: "OK",
    signals.YELLOW: "watch",
    signals.ORANGE: "elevated",
    signals.RED: "critical",
}


def word(signal: signals.Signal) -> str:
    text = signal.word or WORDS[signal.level]
    return text if text == "OK" else text.lower()


def supply_clause(
    supply: signals.Signal,
    at_risk: tuple[float, float] | None,
    delayed: tuple[float, float],
    behind: list[str],
) -> str:
    """'Supply critical: 16–39 % … at risk behind Hormuz, 12 % on a detour'."""
    if at_risk is None:
        return "Supply: no trade data loaded"
    parts = []
    if at_risk[1] > 0:
        where = f" behind {', '.join(behind)}" if behind else ""
        parts.append(f"{signals.pct_range(*at_risk)} of extra-European PE imports at risk{where}")
    if delayed[1] > 0:
        parts.append(f"{signals.pct_range(*delayed)} on a detour")
    if not parts:
        parts.append("no extra-European PE imports pass a closed chokepoint")
    return f"Supply {word(supply)}: " + ", ".join(parts)


def sentence(
    lights: list[signals.Signal],
    at_risk: tuple[float, float] | None,
    delayed: tuple[float, float],
    behind: list[str],
    scenario_label: str,
    as_of: pd.Timestamp,
) -> str:
    by_title = {light.title: light for light in lights}
    clauses = [supply_clause(by_title["Supply"], at_risk, delayed, behind)]
    clauses += [f"{title.lower()} {word(by_title[title])}" for title in ("Price", "Logistics")]
    return "; ".join(clauses) + f" ({scenario_label.lower()}, chokepoints to {as_of:%d %b %Y})."


# One short note per kind of change for the buyer (fixed texts, no forecast).
NOTES = {
    ("chokepoint", "down"): "check the routes through it in Sourcing",
    ("event", "new"): "watch the ports and routes nearby",
    ("storm", "new"): "ships there may slow down or wait",
    ("feedstock", "up"): "feedstock cost up – compare resin offers with it",
    ("feedstock", "down"): "feedstock cost down – a point for price talks",
    ("asia", "up"): "Asian PE price up – compare offers from Asia with it",
    ("asia", "down"): "Asian PE price down – compare offers from Asia with it",
    ("fx", "up"): "euro stronger – dollar-priced imports cheaper in EUR",
    ("fx", "down"): "euro weaker – dollar-priced imports dearer in EUR",
    ("other", "up"): "",
    ("other", "down"): "",
}
GROUPS = {"energy": "feedstock", "gas": "feedstock", "china_futures": "asia"}


def market_note(series_id: str, group: str, change_pct: float) -> str:
    """The buyer note for a market move; DEXUSEU (USD per EUR) up = stronger euro."""
    kind = "fx" if series_id == "DEXUSEU" else GROUPS.get(group, "other")
    return NOTES[(kind, "up" if change_pct > 0 else "down")]
