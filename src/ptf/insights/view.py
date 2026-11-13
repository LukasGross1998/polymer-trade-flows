"""Everything the buyer tabs show, computed from the loaded tables in one place.

The app passes in what it loaded from the warehouse; these functions combine the domains
and return plain values and tables, so the tabs only format and draw.
"""

from dataclasses import dataclass

import pandas as pd

from ptf.insights import exposure, signals
from ptf.insights.config import SourcingConfig
from ptf.markets import indicators
from ptf.shipping.config import MonitorConfig
from ptf.shipping.metrics import latest_status, monitor_table


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
