"""Order planner (spec 010, sourced inputs since spec 015): cost against arrival date.

ship transit time = median time in port at origin + sea days + median time in port at the
destination, where
- sea days  = sea distance (nm) / (average speed at sea (kn) x 24 h), speed from the Fourth
              IMO GHG Study for the chosen container ship size;
- port days = UNCTAD median time in port of container ships, by country.
Not included, because no source gives them: loading and export clearance, waiting for a
sailing, import clearance, delivery to the warehouse, congestion or storm delays. Congestion
and storms are shown as flags. A country without UNCTAD port data has no transit time (n/a).

Combines model (distances), shipping (port status, weather) and the landed cost, so it
lives in the insights layer (ADR-014).
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
    """Sea days and flags per origin region to the focus region.

    `routes` has origin_region, distance_nm and chokepoint_ids (the chokepoints on the route,
    insights.exposure). Columns: origin_region, distance_nm, sea_days, congested,
    storm_on_route.
    """
    rows = []
    destination_congested = focus_region in congested_regions
    for route in routes.to_dict("records"):
        rows.append(
            {
                "origin_region": route["origin_region"],
                "distance_nm": float(route["distance_nm"]),
                "sea_days": sea_days(float(route["distance_nm"]), config.speed),
                "congested": destination_congested or route["origin_region"] in congested_regions,
                "storm_on_route": bool(set(route["chokepoint_ids"]) & storm_chokepoints),
            }
        )
    columns = ["origin_region", "distance_nm", "sea_days", "congested", "storm_on_route"]
    return pd.DataFrame(rows, columns=columns)


def plan(
    landed: pd.DataFrame,
    leads: pd.DataFrame,
    order_date: pd.Timestamp,
    need_by: pd.Timestamp,
    quantity_t: float,
    config: LeadTime,
    freight_known: bool,
) -> pd.DataFrame:
    """Transit time, arrival and on-time flag per supplier; cheapest first.

    `landed` comes from `insights.landed_cost.landed_cost` (one row per exporter country).
    Adds origin_port_days, destination_port_days, lead_days and arrival (NaN / NaT when the
    origin has no sourced port time), on_time (True / False / None = unknown), total_eur and
    recommended: the cheapest on-time supplier, but only when freight is known – a ranking
    without freight would not say which origin is cheapest delivered.
    """
    table = landed.merge(
        leads.drop(columns=["distance_nm"]),
        left_on="exporter_region",
        right_on="origin_region",
        how="inner",
    ).drop(columns=["origin_region"])
    table["origin_port_days"] = table["exporter_iso3"].map(config.port_days.get)
    table["destination_port_days"] = config.port_days.get(config.destination_country)
    table["lead_days"] = (
        table["origin_port_days"] + table["sea_days"] + table["destination_port_days"]
    ).astype(float)
    known = table["lead_days"].notna()
    table["arrival"] = pd.NaT
    table.loc[known, "arrival"] = order_date + pd.to_timedelta(
        table.loc[known, "lead_days"].round(), unit="D"
    )
    table["arrival"] = pd.to_datetime(table["arrival"])
    table["on_time"] = [
        bool(arrival <= need_by) if ok else None
        for arrival, ok in zip(table["arrival"], known, strict=True)
    ]
    table["total_eur"] = table["landed_eur_t"] * quantity_t
    table = table.sort_values("landed_eur_t").reset_index(drop=True)
    table["recommended"] = False
    if freight_known:
        on_time = table[table["on_time"] == True]  # noqa: E712 (None means unknown)
        if not on_time.empty:
            table.loc[on_time.index[0], "recommended"] = True
    return table
