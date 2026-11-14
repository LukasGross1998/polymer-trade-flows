"""Order planner (spec 010): landed cost against arrival date per supplier country.

lead time = origin port days + sea days + destination port days + buffers, where
- sea days = sea distance (nm) / (speed (kn) x 24 h);
- congestion buffer if a monitored port of the origin or destination region is below
  normal (port calls, monitor method);
- storm buffer if a chokepoint on the route has a storm (red) forecast.

Combines model (distances), shipping (port status, weather) and the landed cost, so it
lives in the insights layer (ADR-014). These are planning estimates: average transit times,
one port per region, no real quotes or sailing schedules.
"""

import pandas as pd

from ptf.insights.config import LeadTime

HOURS_PER_DAY = 24


def sea_days(distance_nm: float, speed_knots: float) -> float:
    """Days at sea for a distance at constant speed (1 knot = 1 nautical mile per hour)."""
    return distance_nm / (speed_knots * HOURS_PER_DAY)


def lead_times(
    routes: pd.DataFrame,
    focus_region: str,
    config: LeadTime,
    congested_regions: set[str],
    storm_chokepoints: set[str],
) -> pd.DataFrame:
    """Lead time per origin region to the focus region.

    `routes` has origin_region, distance_nm and chokepoint_ids (the chokepoints on the route,
    insights.exposure). Columns: origin_region, distance_nm, sea_days, port_days, buffer_days,
    lead_days, congested, storm_on_route.
    """
    rows = []
    destination_congested = focus_region in congested_regions
    for route in routes.to_dict("records"):
        congested = destination_congested or route["origin_region"] in congested_regions
        storm = bool(set(route["chokepoint_ids"]) & storm_chokepoints)
        days_at_sea = sea_days(float(route["distance_nm"]), config.speed_knots)
        port_days = config.origin_port_days + config.destination_port_days
        buffer = (config.congestion_buffer_days if congested else 0.0) + (
            config.storm_buffer_days if storm else 0.0
        )
        rows.append(
            {
                "origin_region": route["origin_region"],
                "distance_nm": float(route["distance_nm"]),
                "sea_days": days_at_sea,
                "port_days": port_days,
                "buffer_days": buffer,
                "lead_days": days_at_sea + port_days + buffer,
                "congested": congested,
                "storm_on_route": storm,
            }
        )
    columns = [
        "origin_region",
        "distance_nm",
        "sea_days",
        "port_days",
        "buffer_days",
        "lead_days",
        "congested",
        "storm_on_route",
    ]
    return pd.DataFrame(rows, columns=columns)


def plan(
    landed: pd.DataFrame,
    leads: pd.DataFrame,
    order_date: pd.Timestamp,
    need_by: pd.Timestamp,
    quantity_t: float,
    overland_days: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Landed cost, arrival date and on-time flag per supplier; cheapest first.

    `landed` comes from `insights.landed_cost.landed_cost` (one row per exporter country).
    Adds overland_days (included in lead_days), arrival, on_time, total_eur (landed EUR/t x
    quantity) and recommended (the cheapest on-time supplier, else the earliest arrival).
    """
    table = landed.merge(
        leads.drop(columns=["distance_nm"]),
        left_on="exporter_region",
        right_on="origin_region",
        how="inner",
    ).drop(columns=["origin_region"])
    # Landlocked exporters first travel overland to the region's port (config assumption).
    table["overland_days"] = table["exporter_iso3"].map(overland_days or {}).fillna(0.0)
    table["lead_days"] = table["lead_days"] + table["overland_days"]
    table["arrival"] = order_date + pd.to_timedelta(table["lead_days"].round(), unit="D")
    table["on_time"] = table["arrival"] <= need_by
    table["total_eur"] = table["landed_eur_t"] * quantity_t
    table = table.sort_values("landed_eur_t").reset_index(drop=True)
    on_time = table[table["on_time"]]
    pick = on_time.index[0] if not on_time.empty else table["arrival"].idxmin()
    table["recommended"] = table.index == pick
    return table
