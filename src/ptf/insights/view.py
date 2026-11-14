"""Everything the buyer tabs show, computed from the loaded tables in one place.

The app passes in what it loaded from the warehouse; these functions combine the domains
and return plain values and tables, so the tabs only format and draw.
"""

from dataclasses import dataclass

import pandas as pd

from ptf.insights import exposure, landed_cost, planner, signals
from ptf.insights.config import SourcingConfig
from ptf.markets import indicators
from ptf.model.config import FreightAssumption
from ptf.shipping.config import MonitorConfig
from ptf.shipping.metrics import latest_status, monitor_table, port_table
from ptf.shipping.weather import RED, storm_warnings


@dataclass
class SourcingView:
    year: int
    routes: pd.DataFrame  # extra-regional imports per exporter country with route
    exposed: pd.Series  # per row of `routes`: passes a disrupted chokepoint
    disrupted: list[str]  # names of the disrupted chokepoints on the routes
    exposure_pct: float
    extra_t: float
    intra_share_pct: float
    top3_pct: float


def chokepoint_history(transits: pd.DataFrame, config: MonitorConfig) -> pd.DataFrame:
    """Daily monitor table of all chokepoints (all vessels): rolling mean, baseline, flag."""
    return monitor_table(transits, "total", config)


def disrupted_ids(history: pd.DataFrame) -> set[str]:
    """Chokepoints flagged disrupted on the latest date."""
    status = latest_status(history)
    return set(status.loc[status["is_disrupted"], "location_id"])


def sourcing_view(
    sources: pd.DataFrame,
    distances: pd.DataFrame,
    chokepoints: pd.DataFrame,
    history: pd.DataFrame,
    config: SourcingConfig,
) -> SourcingView:
    region = config.focus_region
    year = exposure.latest_year(sources, region)
    route_table = exposure.route_chokepoints(
        distances, config.passage_chokepoints, chokepoints, region
    )
    routes = exposure.import_routes(sources, route_table, region, year)
    flagged = disrupted_ids(history)
    exposed = exposure.is_exposed(routes, flagged)

    on_routes = {i for ids in routes["chokepoint_ids"] for i in ids} & flagged
    names = dict(zip(chokepoints["chokepoint_id"], chokepoints["chokepoint"], strict=True))
    all_imports = sources[(sources["importer_region"] == region) & (sources["year"] == year)]
    total_t = all_imports["qty_t"].sum()
    extra_t = float(routes["qty_t"].sum())
    return SourcingView(
        year=year,
        routes=routes,
        exposed=exposed,
        disrupted=sorted(names.get(i, i) for i in on_routes),
        exposure_pct=exposure.exposure_share(routes, flagged),
        extra_t=extra_t,
        intra_share_pct=float((total_t - extra_t) / total_t * 100) if total_t else 0.0,
        top3_pct=exposure.top_share(routes, 3),
    )


def traffic_lights(
    market: pd.DataFrame | None, view: SourcingView | None, config: SourcingConfig
) -> list[signals.Signal]:
    """Price, supply and logistics lights; a light without data says so and stays green."""
    lights = []
    if market is not None:
        lights.append(signals.price_signal(indicators.in_currency(market, "EUR"), config.signals))
    else:
        lights.append(signals.Signal("Price", signals.GREEN, "n/a", "no market data yet"))
    if view is not None:
        lights.append(
            signals.supply_signal(view.exposure_pct, view.extra_t, view.year, config.signals)
        )
    else:
        lights.append(signals.Signal("Supply", signals.GREEN, "n/a", "no trade data yet"))
    if market is not None:
        lights.append(signals.logistics_signal(market, config.signals))
    else:
        lights.append(signals.Signal("Logistics", signals.GREEN, "n/a", "no market data yet"))
    return lights


@dataclass
class LandedView:
    year: int
    table: pd.DataFrame  # top suppliers, cheapest first (insights.landed_cost.landed_cost)
    reference_eur_t: float | None  # average price within Europe, EUR/t
    usd_per_eur: float
    price_scale: float
    closure_extra_eur_t: float | None  # Red Sea closure: extra landed cost, Middle East
    duty_source: str  # where the third-country rate comes from


def landed_view(
    sources: pd.DataFrame,
    market: pd.DataFrame | None,
    distances_open: pd.DataFrame,
    distances_closed: pd.DataFrame | None,
    freight: FreightAssumption,
    config: SourcingConfig,
    red_sea_closed: bool,
    freight_factor: float,
    indexed_prices: bool,
    mfn_pct: float | None = None,
) -> LandedView:
    """Landed cost of the largest supplier countries for the chosen route, freight and prices.

    `mfn_pct` is the EU third-country rate from WITS for the selected grade(s); without it
    the configured default applies. Preferential rates always come from the config.
    """
    settings = config.landed_cost
    duty = settings.duty
    if mfn_pct is not None:
        duty = duty.model_copy(update={"default_pct": mfn_pct})
    region = config.focus_region
    year = exposure.latest_year(sources, region)
    fx = None if market is None else indicators.latest(market, settings.fx_series)
    usd_per_eur = fx[1] if fx is not None else 1.0
    scale = 1.0
    if indexed_prices and market is not None:
        scale = landed_cost.price_factor(market, settings.resin_index, year)

    prices = landed_cost.unit_prices(sources, region, year)
    top = prices.nlargest(settings.top_n, "qty_t")

    def compute(distances: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
        return landed_cost.landed_cost(
            rows, distances, freight, duty, region, usd_per_eur, freight_factor, scale
        )

    chosen = distances_closed if red_sea_closed and distances_closed is not None else distances_open
    closure = None
    if distances_closed is not None:
        open_all = landed_cost.weighted_landed(compute(distances_open, prices), "MDE")
        closed_all = landed_cost.weighted_landed(compute(distances_closed, prices), "MDE")
        if open_all is not None and closed_all is not None:
            closure = closed_all - open_all
    reference = landed_cost.reference_price(sources, region, year)
    return LandedView(
        year=year,
        table=compute(chosen, top),
        reference_eur_t=None if reference is None else reference * scale / usd_per_eur,
        usd_per_eur=usd_per_eur,
        price_scale=scale,
        closure_extra_eur_t=closure,
        duty_source=(
            f"third-country duty {duty.default_pct:.2f} % from World Bank WITS"
            if mfn_pct is not None
            else f"third-country duty {duty.default_pct:.1f} % from config (no WITS rate)"
        ),
    )


ALL_GRADES = "all"


def sources_for_grade(by_product: pd.DataFrame, grade: str = ALL_GRADES) -> pd.DataFrame:
    """Import sources summed over the selected PE grade (HS6) or over all grades.

    Returns the columns of `marts.mart_import_sources` that the exposure and landed-cost
    functions use, so they work unchanged per grade (spec 008).
    """
    rows = by_product if grade == ALL_GRADES else by_product[by_product["hs6"] == grade]
    keys = [
        "year",
        "importer_region",
        "exporter_iso3",
        "exporter_name",
        "exporter_region",
        "is_intra_regional",
    ]
    summed = rows.groupby(keys, as_index=False).agg(
        qty_t=("qty_t", "sum"), value_usd=("value_usd", "sum")
    )
    return summed[summed["qty_t"] > 0].reset_index(drop=True)


def mfn_rate(
    eu_duty: pd.DataFrame | None,
    by_product: pd.DataFrame | None,
    grade: str,
    focus_region: str,
) -> float | None:
    """EU third-country rate for one grade, or the import-weighted average over all grades.

    Weights: the focus region's extra-regional tonnes per grade in the latest year.
    """
    if eu_duty is None or eu_duty.empty:
        return None
    rates = dict(zip(eu_duty["hs6"], eu_duty["mfn_pct"], strict=True))
    if grade != ALL_GRADES:
        rate = rates.get(grade)
        return None if rate is None else float(rate)
    if by_product is None:
        return None
    rows = by_product[
        (by_product["importer_region"] == focus_region) & ~by_product["is_intra_regional"]
    ]
    rows = rows[rows["year"] == rows["year"].max()]
    weights = rows.groupby("hs6")["qty_t"].sum()
    weights = weights[weights.index.isin(list(rates))]
    if weights.sum() == 0:
        return None
    return float(sum(rates[h] * w for h, w in weights.items()) / weights.sum())


@dataclass
class PlannerView:
    table: pd.DataFrame  # insights.planner.plan: suppliers with landed cost, arrival, flags
    landed: LandedView
    order_date: pd.Timestamp
    need_by: pd.Timestamp
    quantity_t: float
    europe_arrival: pd.Timestamp


def congested_regions(port_activity: pd.DataFrame | None, config: MonitorConfig) -> set[str]:
    """Regions with a monitored port whose port calls are flagged below normal today."""
    if port_activity is None or port_activity.empty:
        return set()
    status = latest_status(port_table(port_activity, "portcalls", config))
    flagged = set(status.loc[status["is_disrupted"], "location_id"])
    return {p.region for p in config.ports if p.id in flagged and p.region}


def storm_chokepoints(
    weather_table: pd.DataFrame | None, as_of: pd.Timestamp, config: MonitorConfig
) -> set[str]:
    """Chokepoints with a storm (red) forecast from `as_of` on."""
    if weather_table is None or weather_table.empty:
        return set()
    warnings = storm_warnings(weather_table, as_of, config.weather)
    red = warnings[(warnings["level"] == RED) & (warnings["location_type"] == "chokepoint")]
    return set(red["location_id"])


def planner_view(
    landed: LandedView,
    distances: pd.DataFrame,
    chokepoints: pd.DataFrame,
    config: SourcingConfig,
    congested: set[str],
    storms: set[str],
    order_date: pd.Timestamp,
    need_by: pd.Timestamp,
    quantity_t: float,
) -> PlannerView:
    """Lead times on the chosen route and the plan for the landed-cost suppliers."""
    region = config.focus_region
    routes = exposure.route_chokepoints(distances, config.passage_chokepoints, chokepoints, region)
    to_focus = distances.loc[distances["dest_region"] == region, ["origin_region", "distance_nm"]]
    routes = routes.merge(to_focus, on="origin_region")
    leads = planner.lead_times(routes, region, config.lead_time, congested, storms)
    table = planner.plan(
        landed.table, leads, order_date, need_by, quantity_t, config.lead_time.overland_days
    )
    europe = order_date + pd.Timedelta(days=config.lead_time.europe_days)
    return PlannerView(table, landed, order_date, need_by, quantity_t, europe)
