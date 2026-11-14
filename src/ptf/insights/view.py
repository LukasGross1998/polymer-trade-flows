"""Everything the buyer tabs show, computed from the loaded tables in one place.

The app passes in what it loaded from the warehouse; these functions combine the domains
and return plain values and tables, so the tabs only format and draw.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from ptf.insights import exposure, landed_cost, planner, signals
from ptf.insights import scenario as scenario_mod
from ptf.insights.config import SourcingConfig
from ptf.insights.scenario import Scenario
from ptf.markets import indicators
from ptf.model.config import FreightAssumption
from ptf.shipping.config import MonitorConfig
from ptf.shipping.metrics import latest_status, monitor_table, port_table
from ptf.shipping.weather import RED, storm_warnings

WITS_SOURCE = "World Bank WITS (TRAINS), EU MFN applied rate, highest tariff line of the grade"
WITS_URL = "https://wits.worldbank.org/"


@dataclass
class RouteTables:
    """Sea-distance tables (model): all routes open, every detour variant, and the origin keys
    of countries with own export ports (spec 014)."""

    base: pd.DataFrame
    variants: dict[str, pd.DataFrame] = field(default_factory=dict)
    country_keys: dict[str, list[str]] = field(default_factory=dict)

    def table(self, variant: str) -> pd.DataFrame:
        """The variant's table; the base table if the variant was not ingested."""
        if variant == scenario_mod.BASE_VARIANT:
            return self.base
        return self.variants.get(variant, self.base)

    def to_focus_nm(self, variant: str, focus_region: str) -> pd.Series:
        rows = self.table(variant)
        rows = rows[rows["dest_region"] == focus_region]
        return rows.set_index("origin_region")["distance_nm"]


@dataclass
class SourcingView:
    year: int
    routes: pd.DataFrame  # imports per exporter country and port, with route and risk flags
    exposed: pd.Series  # per row of `routes`: at risk or on a detour in the scenario
    disrupted: list[str]  # names of the closed chokepoints on the routes
    exposure_pct: float  # upper bound of the exposed share
    extra_t: float
    intra_share_pct: float
    top3_pct: float
    exposure_low_pct: float = 0.0
    at_risk: tuple[float, float] = (0.0, 0.0)  # % of tonnes, (low, high)
    delayed: tuple[float, float] = (0.0, 0.0)
    scenario: scenario_mod.Scenario | None = None


def chokepoint_history(transits: pd.DataFrame, config: MonitorConfig) -> pd.DataFrame:
    """Daily monitor table of all chokepoints (all vessels): rolling mean, baseline, flag."""
    return monitor_table(transits, "total", config)


def disrupted_ids(history: pd.DataFrame) -> set[str]:
    """Chokepoints flagged disrupted on the latest date."""
    status = latest_status(history)
    return set(status.loc[status["is_disrupted"], "location_id"])


def resolve_scenario(key: str, history: pd.DataFrame | None, config: SourcingConfig) -> Scenario:
    """The route scenario `key`, live status from the monitor's latest chokepoint status."""
    status = None if history is None or history.empty else latest_status(history)
    return scenario_mod.resolve(key, status, config.scenarios, config.chokepoint_detours)


def scenario_routes(
    tables: RouteTables, chokepoints: pd.DataFrame, config: SourcingConfig, scenario: Scenario
) -> pd.DataFrame:
    """Route per origin to the focus region in the scenario, with route_key for merging."""
    table = exposure.route_chokepoints(
        tables.table(scenario.variant),
        config.passage_chokepoints,
        chokepoints,
        config.focus_region,
    )
    return table.assign(route_key=table["origin_region"])


def sourcing_view(
    sources: pd.DataFrame,
    tables: RouteTables,
    chokepoints: pd.DataFrame,
    scenario: Scenario,
    config: SourcingConfig,
) -> SourcingView:
    region = config.focus_region
    year = exposure.latest_year(sources, region)
    route_table = scenario_routes(tables, chokepoints, config, scenario).drop(columns=["route_key"])
    routes = exposure.import_routes(sources, route_table, region, year, tables.country_keys)
    routes = scenario_mod.classify(
        routes, tables.to_focus_nm(scenario_mod.BASE_VARIANT, region), scenario
    )
    exposed = routes["at_risk"] | routes["delayed"]

    on_routes = {i for ids in routes["chokepoint_ids"] for i in ids}
    base_routes = exposure.route_chokepoints(
        tables.base, config.passage_chokepoints, chokepoints, region
    )
    on_routes |= {i for ids in base_routes["chokepoint_ids"] for i in ids}
    names = dict(zip(chokepoints["chokepoint_id"], chokepoints["chokepoint"], strict=True))
    all_imports = sources[(sources["importer_region"] == region) & (sources["year"] == year)]
    total_t = all_imports["qty_t"].sum()
    extra_t = float(exposure.country_tonnes(routes).sum()) if not routes.empty else 0.0
    low, high = exposure.share_range(routes, exposed)
    return SourcingView(
        year=year,
        routes=routes,
        exposed=exposed,
        disrupted=sorted(names.get(i, i) for i in on_routes & scenario.closed),
        exposure_pct=high,
        extra_t=extra_t,
        intra_share_pct=float((total_t - extra_t) / total_t * 100) if total_t else 0.0,
        top3_pct=exposure.top_share(routes, 3),
        exposure_low_pct=low,
        at_risk=exposure.share_range(routes, routes["at_risk"]),
        delayed=exposure.share_range(routes, routes["delayed"]),
        scenario=scenario,
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
            signals.supply_signal(
                (view.exposure_low_pct, view.exposure_pct),
                view.at_risk,
                view.delayed,
                view.extra_t,
                view.year,
                view.scenario.label if view.scenario is not None else "Live status",
                config.signals,
            )
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
    table: pd.DataFrame  # top suppliers per export port, cheapest first, with risk flags
    reference_eur_t: float | None  # average price within Europe, EUR/t
    usd_per_eur: float
    price_scale: float
    closure_extra_eur_t: float | None  # scenario vs. all routes open: extra cost, Middle East
    duty_source: str  # where the third-country rate comes from
    freight_known: bool = False  # a sourced freight rate exists (spec 015)
    scenario: Scenario | None = None


def port_label(name: str, port: str, n_ports: int) -> str:
    """'Saudi Arabia (Yanbu)' for a country with several export ports, else the name."""
    return f"{name} ({port})" if n_ports > 1 else name


def landed_view(
    sources: pd.DataFrame,
    market: pd.DataFrame | None,
    tables: RouteTables,
    chokepoints: pd.DataFrame,
    freight: FreightAssumption | None,
    config: SourcingConfig,
    scenario: Scenario,
    indexed_prices: bool,
    mfn_pct: float | None = None,
    on: date | None = None,
    freight_factor: float = 1.0,
) -> LandedView:
    """Landed cost of the largest supplier countries in the route scenario (spec 014).

    `mfn_pct` is the EU third-country rate from WITS for the selected grade(s); without it
    the configured default applies. Preferential rates always come from the config. Each
    row is flagged at_risk / delayed / reduced as in the sourcing view.
    """
    settings = config.landed_cost
    duty = settings.duty
    if mfn_pct is not None:
        duty = duty.with_default(mfn_pct, WITS_SOURCE, WITS_URL, on or date.today())
    region = config.focus_region
    year = exposure.latest_year(sources, region)
    fx = None if market is None else indicators.latest(market, settings.fx_series)
    usd_per_eur = fx[1] if fx is not None else 1.0
    scale = 1.0
    if indexed_prices and market is not None:
        scale = landed_cost.price_factor(market, settings.resin_index, year)

    prices = exposure.with_route_keys(
        landed_cost.unit_prices(sources, region, year), tables.country_keys
    )
    top_countries = exposure.country_tonnes(prices).nlargest(settings.top_n).index
    top = prices[prices["exporter_iso3"].isin(top_countries)]

    def compute(variant: str, rows: pd.DataFrame) -> pd.DataFrame:
        return landed_cost.landed_cost(
            rows,
            tables.table(variant),
            freight,
            duty,
            region,
            usd_per_eur,
            freight_factor,
            scale,
            on,
        )

    closure = None
    if freight is not None and scenario.variant != scenario_mod.BASE_VARIANT:
        open_all = landed_cost.weighted_landed(compute(scenario_mod.BASE_VARIANT, prices), "MDE")
        closed_all = landed_cost.weighted_landed(compute(scenario.variant, prices), "MDE")
        if open_all is not None and closed_all is not None:
            closure = closed_all - open_all
    table = compute(scenario.variant, top)
    routes = scenario_routes(tables, chokepoints, config, scenario)[
        ["route_key", "chokepoint_ids", "route"]
    ]
    table = table.merge(routes, on="route_key", how="left")
    table["chokepoint_ids"] = table["chokepoint_ids"].apply(
        lambda ids: ids if isinstance(ids, list) else []
    )
    table = scenario_mod.classify(
        table, tables.to_focus_nm(scenario_mod.BASE_VARIANT, region), scenario
    )
    table["exporter_name"] = [
        port_label(n, p, k)
        for n, p, k in zip(table["exporter_name"], table["port"], table["n_ports"], strict=True)
    ]
    reference = landed_cost.reference_price(sources, region, year)
    return LandedView(
        year=year,
        table=table.sort_values("landed_usd_t").reset_index(drop=True),
        reference_eur_t=None if reference is None else reference * scale / usd_per_eur,
        usd_per_eur=usd_per_eur,
        price_scale=scale,
        closure_extra_eur_t=closure,
        duty_source=(
            f"third-country duty {duty.default_pct.value:.2f} % from World Bank WITS"
            if mfn_pct is not None
            else f"third-country duty {duty.default_pct.value:.1f} % from EU TARIC"
        ),
        freight_known=freight is not None,
        scenario=scenario,
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
    tables: RouteTables,
    chokepoints: pd.DataFrame,
    config: SourcingConfig,
    congested: set[str],
    storms: set[str],
    order_date: pd.Timestamp,
    need_by: pd.Timestamp,
    quantity_t: float,
) -> PlannerView:
    """Lead times in the landed view's scenario and the plan for its suppliers."""
    region = config.focus_region
    scenario = landed.scenario or resolve_scenario(scenario_mod.LIVE, None, config)
    routes = scenario_routes(tables, chokepoints, config, scenario).drop(columns=["route_key"])
    routes = routes[routes["distance_nm"].notna()]
    leads = planner.lead_times(routes, region, config.lead_time, congested, storms)
    table = planner.plan(
        landed.table,
        leads,
        order_date,
        need_by,
        quantity_t,
        config.lead_time,
        landed.freight_known,
    )
    # Congestion by the exporter's region (country ports have keys like 'SAU:Yanbu').
    table["congested"] = (region in congested) | table["exporter_region"].isin(congested)
    return PlannerView(table, landed, order_date, need_by, quantity_t)
