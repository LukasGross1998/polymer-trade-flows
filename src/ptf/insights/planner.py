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

import math

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
    own_before_days: float = 0.0,
    own_after_days: float = 0.0,
) -> pd.DataFrame:
    """Transit time, arrival and on-time flag per supplier; cheapest first.

    `landed` comes from `insights.landed_cost.landed_cost` (one row per exporter country).
    Adds origin_port_days, destination_port_days, lead_days and arrival (NaN / NaT when the
    origin has no sourced port time), on_time (True / False / None = unknown), total_eur and
    recommended: the cheapest on-time supplier, but only when freight is known – a ranking
    without freight would not say which origin is cheapest delivered. Rows flagged at_risk
    (spec 014) or not sourceable (spec 016) are never recommended; at-risk rows are never
    on time.

    Spec 016: the buyer's own lead days come before departure (`own_before_days`, production
    and booking) and after the ship's arrival (`own_after_days`, customs and delivery).
    arrival is the ship's arrival; at_site = arrival + own_after_days is compared with the
    need-by date; latest_order = need_by − all days; containers = quantity / the sourced
    maximum payload of a 40-foot box, rounded up (a lower bound).
    """
    if "route_key" not in landed.columns:
        landed = landed.assign(route_key=landed["exporter_region"])
    table = landed.merge(
        leads.drop(columns=["distance_nm"]),
        left_on="route_key",
        right_on="origin_region",
        how="inner",
    ).drop(columns=["origin_region"])
    table["origin_port_days"] = table["exporter_iso3"].map(config.port_days.get)
    table["destination_port_days"] = config.port_days.get(config.destination_country)
    table["lead_days"] = (
        table["origin_port_days"] + table["sea_days"] + table["destination_port_days"]
    ).astype(float)
    known = table["lead_days"].notna()
    table["total_days"] = own_before_days + table["lead_days"] + own_after_days
    table["arrival"] = pd.NaT
    table["at_site"] = pd.NaT
    table["latest_order"] = pd.NaT
    days = pd.to_timedelta((own_before_days + table.loc[known, "lead_days"]).round(), unit="D")
    table.loc[known, "arrival"] = order_date + days
    table.loc[known, "at_site"] = order_date + pd.to_timedelta(
        table.loc[known, "total_days"].round(), unit="D"
    )
    table.loc[known, "latest_order"] = need_by - pd.to_timedelta(
        table.loc[known, "total_days"].round(), unit="D"
    )
    for column in ["arrival", "at_site", "latest_order"]:
        table[column] = pd.to_datetime(table[column])
    at_risk = table["at_risk"] if "at_risk" in table.columns else pd.Series(False, table.index)
    # At risk (behind a closed chokepoint without a sea detour, spec 014): never on time.
    table["on_time"] = [
        False if risk else (bool(at_site <= need_by) if ok else None)
        for at_site, ok, risk in zip(table["at_site"], known, at_risk, strict=True)
    ]
    cost = "total_eur_t" if "total_eur_t" in table.columns else "landed_eur_t"
    table["total_eur"] = table[cost] * quantity_t
    payload = config.container_payload_t
    table["containers"] = (
        math.ceil(quantity_t / payload.value) if payload is not None and payload.value > 0 else None
    )
    table = table.sort_values(cost).reset_index(drop=True)
    table["recommended"] = False
    usable = table["sourceable"] if "sourceable" in table.columns else True
    if freight_known:
        on_time = table[(table["on_time"] == True) & usable]  # noqa: E712 (None = unknown)
        if not on_time.empty:
            table.loc[on_time.index[0], "recommended"] = True
    return table


def sea_day_range(sea_days_at_speed: float, speed: float, config: LeadTime) -> tuple[float, float]:
    """Sea days with the fastest and the slowest container ship size of the sourced speed
    table (spec 018): the uncertainty band of the transit."""
    speeds = list(config.speed_knots.values.values())
    distance_nm = sea_days_at_speed * speed * HOURS_PER_DAY
    return sea_days(distance_nm, max(speeds)), sea_days(distance_nm, min(speeds))


def with_transit_range(table: pd.DataFrame, config: LeadTime) -> pd.DataFrame:
    """Adds arrival_early and arrival_late (fastest / slowest ship size) to a plan."""
    table = table.copy()
    early, late = [], []
    for row in table.to_dict("records"):
        if pd.isna(row["arrival"]):
            early.append(pd.NaT)
            late.append(pd.NaT)
            continue
        fast, slow = sea_day_range(float(row["sea_days"]), config.speed, config)
        early.append(row["arrival"] + pd.Timedelta(days=round(fast - row["sea_days"])))
        late.append(row["arrival"] + pd.Timedelta(days=round(slow - row["sea_days"])))
    table["arrival_early"] = pd.to_datetime(pd.Series(early, index=table.index))
    table["arrival_late"] = pd.to_datetime(pd.Series(late, index=table.index))
    return table
