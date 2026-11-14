"""What matters for the focus region's buyer (spec 013): regions, chokepoints, ports, series.

- relevant supplier regions: the focus region and every region with at least
  `min_region_share` % of its extra-regional imports;
- relevant chokepoints: those on the sea routes from these regions, plus configured extras
  (e.g. Dover Strait on the approach to Rotterdam and Antwerp);
- relevant ports: the monitored ports in relevant regions;
- relevant disruption events: those within `event_radius_km` of a relevant chokepoint or port.
"""

import math
from dataclasses import dataclass, field

import pandas as pd

from ptf.insights.config import Relevance as RelevanceConfig
from ptf.shipping.config import PortConfig

EARTH_RADIUS_KM = 6371.0


@dataclass
class Relevance:
    regions: set[str] = field(default_factory=set)
    chokepoints: set[str] = field(default_factory=set)
    ports: set[str] = field(default_factory=set)
    series: list[str] = field(default_factory=list)


def relevant_regions(routes: pd.DataFrame, focus_region: str, min_share_pct: float) -> set[str]:
    """Focus region plus exporter regions with at least `min_share_pct` of the tonnes."""
    total = routes["qty_t"].sum()
    if total == 0:
        return {focus_region}
    shares = routes.groupby("exporter_region")["qty_t"].sum() / total * 100
    return {focus_region} | set(shares[shares >= min_share_pct].index)


def build(
    routes: pd.DataFrame,
    focus_region: str,
    ports: list[PortConfig],
    config: RelevanceConfig,
) -> Relevance:
    """Relevance from the import routes (insights.exposure.import_routes) and the config."""
    regions = relevant_regions(routes, focus_region, config.min_region_share)
    on_routes = routes[routes["exporter_region"].isin(regions)]
    chokepoints = {i for ids in on_routes["chokepoint_ids"] for i in ids}
    return Relevance(
        regions=regions,
        chokepoints=chokepoints | set(config.extra_chokepoints),
        ports={p.id for p in ports if p.region in regions},
        series=list(config.series),
    )


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine formula)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def near_any(events: pd.DataFrame, points: pd.DataFrame, radius_km: float) -> pd.Series:
    """True for events within `radius_km` of any point (columns lat, lon)."""
    coordinates = list(zip(points["lat"], points["lon"], strict=True))
    return pd.Series(
        [
            any(
                distance_km(e_lat, e_lon, p_lat, p_lon) <= radius_km for p_lat, p_lon in coordinates
            )
            for e_lat, e_lon in zip(events["lat"], events["lon"], strict=True)
        ],
        index=events.index,
        dtype=bool,
    )


def chokepoint_dependency(
    routes: pd.DataFrame,
    distances_open: pd.DataFrame,
    distances_closed: pd.DataFrame | None,
    focus_region: str,
    speed_knots: float,
) -> pd.DataFrame:
    """Per chokepoint on the import routes: share of extra-regional tonnes passing it and the
    volume-weighted extra sea days if the Red Sea route is closed (None without a detour).

    Columns: chokepoint_id, share_pct, extra_days.
    """
    total = routes["qty_t"].sum()
    by_region = routes.groupby("exporter_region")["qty_t"].sum()
    extra = pd.Series(0.0, index=by_region.index)
    if distances_closed is not None:

        def to_focus(table: pd.DataFrame) -> pd.Series:
            rows = table[table["dest_region"] == focus_region]
            return rows.set_index("origin_region")["distance_nm"]

        delta_nm = (to_focus(distances_closed) - to_focus(distances_open)).reindex(by_region.index)
        extra = delta_nm.fillna(0.0) / (speed_knots * 24)
    rows = []
    for chokepoint in sorted({i for ids in routes["chokepoint_ids"] for i in ids}):
        passing = routes[routes["chokepoint_ids"].apply(lambda ids, c=chokepoint: c in ids)]
        tonnes = passing.groupby("exporter_region")["qty_t"].sum()
        weighted = float((extra.reindex(tonnes.index) * tonnes).sum() / tonnes.sum())
        rows.append(
            {
                "chokepoint_id": chokepoint,
                "share_pct": float(tonnes.sum() / total * 100) if total else 0.0,
                "extra_days": weighted if weighted > 0.5 else None,
            }
        )
    return pd.DataFrame(rows, columns=["chokepoint_id", "share_pct", "extra_days"])
