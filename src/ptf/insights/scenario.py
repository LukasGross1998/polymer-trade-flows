"""Route scenarios (spec 014): which chokepoints are closed, and what that does to each route.

Two kinds of chokepoint risk:
- a closed chokepoint with a detour (Bab el-Mandeb and Suez: around the Cape) costs sea days;
  the scenario then uses the route variant that avoids it (`chokepoint_detours`);
- a closed chokepoint without a sea detour (Hormuz) leaves the volume behind it *at risk*:
  availability uncertain.

Whether a route is on a detour or at risk is read from the distance tables, not assumed: a
route that still passes a closed chokepoint in the scenario's variant (or has no sea path)
is at risk; a route that got longer is delayed.

One scenario applies to all tabs. "Live status" derives it from the monitor: closed when the
7-day traffic is at least `closed_below_pct` below normal, reduced when only flagged.
"""

from dataclasses import dataclass

import pandas as pd

from ptf.insights.config import ScenarioSettings

LIVE = "live"
BASE_VARIANT = "base"


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    closed: frozenset[str]  # chokepoint ids
    reduced: frozenset[str]  # traffic below normal, not closed (live status only)
    variant: str  # distance table: "base", a detour variant or "a+b"


ALL_OPEN = Scenario("all_open", "All routes open", frozenset(), frozenset(), BASE_VARIANT)


def options(settings: ScenarioSettings) -> list[dict[str, str]]:
    """Dropdown options: live status first, then the presets."""
    return [{"label": "Live status", "value": LIVE}] + [
        {"label": preset.label, "value": key} for key, preset in settings.presets.items()
    ]


def variant_for(closed: frozenset[str], detours: dict[str, str]) -> str:
    """Distance variant that avoids all closed chokepoints that have a detour."""
    names = sorted({detours[c] for c in closed if c in detours})
    return "+".join(names) if names else BASE_VARIANT


def resolve(
    key: str,
    status: pd.DataFrame | None,
    settings: ScenarioSettings,
    detours: dict[str, str],
) -> Scenario:
    """The scenario `key`; for live status `status` is the monitor's latest status per
    chokepoint (location_id, deviation_pct, is_disrupted). Unknown keys fall back to live."""
    if key in settings.presets:
        preset = settings.presets[key]
        closed = frozenset(preset.closed)
        return Scenario(key, preset.label, closed, frozenset(), variant_for(closed, detours))
    closed_ids: set[str] = set()
    reduced_ids: set[str] = set()
    if status is not None and not status.empty:
        for row in status.to_dict("records"):
            if row["deviation_pct"] <= -settings.closed_below_pct:
                closed_ids.add(row["location_id"])
            elif row["is_disrupted"]:
                reduced_ids.add(row["location_id"])
    closed = frozenset(closed_ids)
    return Scenario(
        LIVE, "Live status", closed, frozenset(reduced_ids), variant_for(closed, detours)
    )


def classify(
    routes: pd.DataFrame, base_nm: pd.Series, scenario: Scenario, tolerance_nm: float = 1.0
) -> pd.DataFrame:
    """Risk of each route under the scenario.

    `routes` has route_key, distance_nm and chokepoint_ids from the scenario's distance table;
    `base_nm` is the distance per route_key with all routes open. Adds at_risk (passes a closed
    chokepoint or has no sea path), delayed (on a detour: longer than with all routes open)
    and reduced (passes a chokepoint with reduced traffic).
    """
    table = routes.copy()
    passes_closed = table["chokepoint_ids"].apply(lambda ids: bool(set(ids) & scenario.closed))
    base = table["route_key"].map(base_nm)
    # No sea path in the scenario although one exists with all routes open (e.g. out of the
    # Red Sea with Suez and Bab el-Mandeb closed). Origins without any known route (rest of
    # world) are not flagged.
    no_path = table["distance_nm"].isna() & base.notna()
    table["at_risk"] = passes_closed | no_path
    table["delayed"] = ~table["at_risk"] & (table["distance_nm"] > base + tolerance_nm)
    table["reduced"] = table["chokepoint_ids"].apply(lambda ids: bool(set(ids) & scenario.reduced))
    return table
