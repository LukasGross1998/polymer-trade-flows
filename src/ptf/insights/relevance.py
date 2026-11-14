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
from ptf.insights.exposure import share_range
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
    countries = routes.drop_duplicates("exporter_iso3") if "exporter_iso3" in routes else routes
    total = countries["qty_t"].sum()
    if total == 0:
        return {focus_region}
    shares = countries.groupby("exporter_region")["qty_t"].sum() / total * 100
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
    tables: dict[str, pd.DataFrame],
    detours: dict[str, str],
    focus_region: str,
    speed_knots: float,
) -> pd.DataFrame:
    """Per chokepoint on the import routes (all routes open): the share of extra-regional
    tonnes passing it and, if it has a sea detour, the extra sea days via that detour.

    `routes` are the import routes with all routes open (route_key, chokepoint_ids, qty_t,
    exporter_iso3); `tables` maps "base" and each detour variant to its distance table.
    Extra days per country = the largest extra distance over its ports that pass the
    chokepoint (ports' shares are unknown), volume-weighted over countries. Without a detour
    (e.g. Hormuz) extra_days is None and has_detour False: the volume is at risk instead.

    Columns: chokepoint_id, share_low_pct, share_pct, has_detour, extra_days.
    """

    def to_focus(table: pd.DataFrame) -> pd.Series:
        rows = table[table["dest_region"] == focus_region]
        return rows.set_index("origin_region")["distance_nm"]

    base = to_focus(tables["base"])
    rows = []
    for chokepoint in sorted({i for ids in routes["chokepoint_ids"] for i in ids}):
        passing = routes["chokepoint_ids"].apply(lambda ids, c=chokepoint: c in ids)
        low, high = share_range(routes, passing)
        variant = detours.get(chokepoint)
        extra = None
        if variant is not None and variant in tables:
            delta_nm = to_focus(tables[variant]) - base
            subset = routes[passing].copy()
            subset["extra_days"] = subset["route_key"].map(delta_nm) / (speed_knots * 24)
            per_country = subset.groupby("exporter_iso3").agg(
                extra_days=("extra_days", "max"), qty_t=("qty_t", "first")
            )
            per_country = per_country[per_country["extra_days"].notna()]
            if not per_country.empty and per_country["qty_t"].sum() > 0:
                extra = float(
                    (per_country["extra_days"] * per_country["qty_t"]).sum()
                    / per_country["qty_t"].sum()
                )
        rows.append(
            {
                "chokepoint_id": chokepoint,
                "share_low_pct": low,
                "share_pct": high,
                "has_detour": variant is not None,
                "extra_days": extra,
            }
        )
    columns = ["chokepoint_id", "share_low_pct", "share_pct", "has_detour", "extra_days"]
    return pd.DataFrame(rows, columns=columns)
