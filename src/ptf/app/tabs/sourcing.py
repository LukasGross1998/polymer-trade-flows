"""Tab "Sourcing": whom does Europe depend on, and which imports pass a disrupted chokepoint?

Combines the BACI import sources with the sea routes and today's chokepoint status
(`ptf.insights`, spec 006).
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, html

from ptf.app import charts, theme
from ptf.app.data import AppData, AppState
from ptf.app.tabs import prices as prices_tab
from ptf.insights import exposure, signals, sourceable
from ptf.insights.scenario import LIVE
from ptf.insights.view import ALL_GRADES, SourcingView

LEVEL_TONES = {
    signals.GREEN: theme.GOOD,
    signals.YELLOW: theme.WARNING,
    signals.ORANGE: theme.ELEVATED,
    signals.RED: theme.CRITICAL,
}


def layout(data: AppData) -> html.Div:
    if data.sourcing is None:
        return charts.no_data("No trade data or sea routes loaded yet.")
    # Full-width charts: the route labels of the Sankey need the room.
    card = {**theme.CARD, "marginBottom": "16px"}
    return html.Div(
        [
            theme.method_panel(
                f"Imports of polyethylene (HS 3901) into Europe from outside the region, CEPII "
                f"BACI {data.sourcing.year} (latest year available). Routes: shortest sea route "
                "from one representative port per region (searoute), or from the country's own "
                "export ports where a source names them (Egypt, Israel, Saudi Arabia). "
                "Colours: in the route scenario chosen above the route is at "
                "risk (it passes a closed chokepoint without a sea detour, e.g. Hormuz) or on a "
                "detour (e.g. around the Cape). Saudi Arabia ships from Al Jubail and Yanbu with "
                "unknown shares: its tonnes count once, shares are ranges.",
            ),
            html.Div(id="src-kpis", style=theme.ROW),
            html.Div(charts.graph("src-sankey"), style=card),
            html.Div(charts.graph("src-suppliers"), style=card),
            html.Div(charts.graph("src-monthly"), style=card),
        ]
    )


def monthly_figure(data: AppData, grade: str = ALL_GRADES, top: int = 5) -> go.Figure:
    """EU27 imports from outside the EU per month (Comext, spec 019): the five largest
    origins of the last 24 months and "Other", stacked bars in thousand tonnes."""
    title = "EU imports from outside the EU per month (Eurostat Comext, thousand tonnes)"
    monthly = data.eu_imports
    if monthly is None or monthly.empty:
        return prices_tab.empty_figure(title, "No Comext data loaded yet.")
    if grade != ALL_GRADES:
        monthly = monthly[monthly["hs6"] == grade]
    months = sorted(monthly["month"].unique())[-24:]
    rows = monthly[monthly["month"].isin(months)]
    totals = rows.groupby("exporter_name")["qty_t"].sum().sort_values(ascending=False)
    leaders = list(totals.index[:top])
    rows = rows.assign(
        origin=rows["exporter_name"].where(rows["exporter_name"].isin(leaders), "Other")
    )
    table = rows.groupby(["month", "origin"], as_index=False)["qty_t"].sum()
    fig = go.Figure()
    colours = [*theme.SERIES, theme.GRID]
    for colour, origin in zip(colours, [*leaders, "Other"], strict=False):
        one = table[table["origin"] == origin]
        fig.add_trace(
            go.Bar(
                x=one["month"],
                y=one["qty_t"] / 1e3,
                name=origin,
                marker={"color": colour},
                hovertemplate="%{x}: %{y:,.0f} thousand t<extra>" + origin + "</extra>",
            )
        )
    fig.update_layout(barmode="stack", hovermode="closest")
    fig.update_yaxes(title={"text": "thousand tonnes", "font": {"color": theme.MUTED}})
    return charts.base_layout(fig, height=340, title=title)


def kpi_values(view: SourcingView, data: AppData) -> list[dict[str, str]]:
    level = signals.level(view.exposure_pct, data.sourcing_config.signals.supply)
    countries = exposure.country_tonnes(view.routes)
    names = view.routes.drop_duplicates("exporter_iso3").set_index("exporter_iso3")["exporter_name"]
    top = [str(names[i]) for i in countries.nlargest(3).index]
    return [
        {
            "label": "Imports from outside Europe",
            "value": f"{view.extra_t / 1e6:,.1f} Mt",
            "note": f"BACI {view.year}",
        },
        {
            "label": "Sourced within Europe",
            "value": f"{view.intra_share_pct:.0f} %",
            "note": "of all imports of European countries",
        },
        {
            "label": "At risk or on a detour",
            "value": signals.pct_range(view.exposure_low_pct, view.exposure_pct),
            "tone": LEVEL_TONES[level],
            "note": f"at risk {signals.pct_range(*view.at_risk)}, on a detour "
            f"{signals.pct_range(*view.delayed)}; closed: "
            + (", ".join(view.disrupted) or "none on the routes"),
        },
        {
            "label": "Top-3 supplier countries",
            "value": f"{view.top3_pct:.0f} %",
            "note": ", ".join(top),
        },
    ]


def country_states(view: SourcingView, blocked: set[str]) -> dict[str, str]:
    """Route encoding per exporter country (theme): not sourceable, at risk, detour or open.
    A country with several ports is at risk / on a detour if any of its ports is."""
    states = {}
    for iso3, group in view.routes.groupby("exporter_iso3"):
        states[str(iso3)] = theme.route_state(
            bool(group["at_risk"].any()), bool(group["delayed"].any()), iso3 not in blocked
        )
    return states


def sankey_figure(
    view: SourcingView,
    blocked: set[str] | None = None,
    destinations: pd.DataFrame | None = None,
) -> go.Figure:
    """Exporter region -> route -> destination in Europe, links coloured with the route
    encoding. A country with several export ports counts once, its route reads "A or B (port
    shares unknown)". `destinations` (exporter_iso3, destination, qty_t, spec 018) splits the
    right column; without it the right column is "Europe"."""
    routes = exposure.by_country(view.routes.assign(exposed=view.exposed), "exposed")
    states = country_states(view, blocked or set())
    routes["state"] = routes["exporter_iso3"].map(states)
    routes["region"] = routes["exporter_region"].map(theme.region_name)
    grouped = routes.groupby(["region", "route", "state"], as_index=False)
    by_route = grouped.agg(qty_t=("qty_t", "sum")).sort_values("qty_t", ascending=False)
    regions = list(dict.fromkeys(by_route["region"]))
    route_names = list(dict.fromkeys(by_route["route"]))
    if destinations is not None and not destinations.empty:
        flows = destinations.merge(routes[["exporter_iso3", "route", "state"]], on="exporter_iso3")
        to_europe = flows.groupby(["route", "state", "destination"], as_index=False).agg(
            qty_t=("qty_t", "sum")
        )
    else:
        to_europe = by_route.groupby(["route", "state"], as_index=False).agg(qty_t=("qty_t", "sum"))
        to_europe["destination"] = "Europe"
    ends = list(to_europe.groupby("destination")["qty_t"].sum().sort_values(ascending=False).index)
    labels = regions + route_names + ends
    index = {name: i for i, name in enumerate(labels)}

    def colour(state: str) -> str:
        return theme.with_alpha(theme.ROUTE_COLOURS[state], 0.55)

    source, target, value, colours = [], [], [], []
    for row in by_route.to_dict("records"):
        source.append(index[row["region"]])
        target.append(index[row["route"]])
        value.append(row["qty_t"] / 1e3)
        colours.append(colour(row["state"]))
    for row in to_europe.to_dict("records"):
        if row["route"] not in index:
            continue
        source.append(index[row["route"]])
        target.append(index[row["destination"]])
        value.append(row["qty_t"] / 1e3)
        colours.append(colour(row["state"]))

    fig = go.Figure(
        go.Sankey(
            node={
                "label": labels,
                "pad": 14,
                "thickness": 14,
                "color": theme.INK_SECONDARY,
                "line": {"width": 0},
            },
            link={
                "source": source,
                "target": target,
                "value": value,
                "color": colours,
                "hovertemplate": (
                    "%{source.label} → %{target.label}: %{value:,.0f} thousand t<extra></extra>"
                ),
            },
        )
    )
    return charts.base_layout(
        fig,
        height=460,
        title="Import routes: region → route → destination in Europe (thousand tonnes)",
    )


def not_sourceable(view: SourcingView, data: AppData) -> set[str]:
    countries = exposure.country_tonnes(view.routes).rename("qty_t").reset_index()
    table = sourceable.classify(countries, data.sourcing_config)
    return set(table.loc[~table["sourceable"], "exporter_iso3"])


def suppliers_figure(
    view: SourcingView, blocked: set[str] | None = None, top: int = 15
) -> go.Figure:
    """One bar per supplier country, sorted by tonnes and coloured with the route encoding;
    the smallest countries are summed into "Other" (spec 018)."""
    countries = exposure.by_country(view.routes.assign(exposed=view.exposed), "exposed")
    states = country_states(view, blocked or set())
    table = exposure.top_with_other(countries, top)
    table["state"] = table["exporter_iso3"].map(states).fillna(theme.ROUTE_OPEN)
    table = table.iloc[::-1]  # largest on top
    share = table["qty_t"] / view.extra_t * 100
    fig = go.Figure()
    for state in [theme.ROUTE_OPEN, theme.ROUTE_DETOUR, theme.ROUTE_AT_RISK, theme.ROUTE_BLOCKED]:
        rows = table[table["state"] == state]
        if rows.empty:
            continue
        fig.add_trace(
            go.Bar(
                y=rows["exporter_name"],
                x=rows["qty_t"] / 1e3,
                orientation="h",
                name=theme.route_label(state),
                marker={"color": theme.ROUTE_COLOURS[state]},
                customdata=share[rows.index],
                hovertemplate="%{y}: %{x:,.0f} thousand t (%{customdata:.1f} %)<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack", hovermode="closest")
    fig.update_yaxes(categoryorder="array", categoryarray=list(table["exporter_name"]))
    fig.update_xaxes(title={"text": "thousand tonnes", "font": {"color": theme.MUTED}})
    return charts.base_layout(
        fig,
        height=max(320, 26 * len(table) + 80),
        title=f"Supplier countries outside Europe, {view.year} (largest {top}, then Other)",
    )


def destinations(data: AppData, view: SourcingView, grade: str) -> pd.DataFrame | None:
    """Destination groups for all grades only: the bilateral mart has no grade split."""
    if data.bilateral is None or grade != ALL_GRADES:
        return None
    return exposure.destination_tonnes(
        data.bilateral,
        data.sourcing_config.focus_region,
        view.year,
        data.sourcing_config.destinations,
    )


def update(data: AppData, grade: str = ALL_GRADES, scenario: str = LIVE) -> charts.Outputs:
    view = data.sourcing_for(grade, scenario)
    blocked = set() if view is None else not_sourceable(view, data)
    if view is None or view.routes.empty:
        return (
            [charts.no_data("No imports of this grade from outside Europe.")],
            go.Figure(),
            go.Figure(),
            monthly_figure(data, grade),
        )
    return (
        charts.tiles(kpi_values(view, data)),
        sankey_figure(view, blocked, destinations(data, view, grade)),
        suppliers_figure(view, blocked, data.sourcing_config.top_suppliers),
        monthly_figure(data, grade),
    )


def register(app: Dash, state: AppState) -> None:
    if state.data.sourcing is None:
        return

    @app.callback(
        Output("src-kpis", "children"),
        Output("src-sankey", "figure"),
        Output("src-suppliers", "figure"),
        Output("src-monthly", "figure"),
        Input("grade", "value"),
        Input("scenario", "value"),
        Input("data-version", "data"),
    )
    def _update(grade: str, scenario: str, _version: int) -> charts.Outputs:
        return update(state.data, grade, scenario)
