"""Tab "Sourcing": whom does Europe depend on, and which imports pass a disrupted chokepoint?

Combines the BACI import sources with the sea routes and today's chokepoint status
(`ptf.insights`, spec 006).
"""

import plotly.graph_objects as go
from dash import Dash, Input, Output, html

from ptf.app import charts, theme
from ptf.app.data import AppData, AppState
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
            html.Div(charts.graph("src-treemap"), style=card),
        ]
    )


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


def sankey_figure(view: SourcingView, blocked: set[str] | None = None) -> go.Figure:
    """Exporter region -> route -> Europe, links coloured with the route encoding. A country
    with several export ports counts once, its route reads "A or B (port shares unknown)"."""
    routes = exposure.by_country(view.routes.assign(exposed=view.exposed), "exposed")
    states = country_states(view, blocked or set())
    routes["state"] = routes["exporter_iso3"].map(states)
    routes["region"] = routes["exporter_region"].map(theme.region_name)
    grouped = routes.groupby(["region", "route", "state"], as_index=False)
    by_route = grouped.agg(qty_t=("qty_t", "sum")).sort_values("qty_t", ascending=False)
    regions = list(dict.fromkeys(by_route["region"]))
    route_names = list(dict.fromkeys(by_route["route"]))
    labels = regions + route_names + ["Europe"]
    index = {name: i for i, name in enumerate(labels)}

    def colour(state: str) -> str:
        return theme.with_alpha(theme.ROUTE_COLOURS[state], 0.55)

    source, target, value, colours = [], [], [], []
    for row in by_route.to_dict("records"):
        source.append(index[row["region"]])
        target.append(index[row["route"]])
        value.append(row["qty_t"] / 1e3)
        colours.append(colour(row["state"]))
    to_europe = by_route.groupby(["route", "state"], as_index=False).agg(qty_t=("qty_t", "sum"))
    for row in to_europe.to_dict("records"):
        source.append(index[row["route"]])
        target.append(index["Europe"])
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
        title="Import routes into Europe: region → route → Europe (thousand tonnes)",
    )


def not_sourceable(view: SourcingView, data: AppData) -> set[str]:
    countries = exposure.country_tonnes(view.routes).rename("qty_t").reset_index()
    table = sourceable.classify(countries, data.sourcing_config)
    return set(table.loc[~table["sourceable"], "exporter_iso3"])


def treemap_figure(view: SourcingView, blocked: set[str] | None = None) -> go.Figure:
    """Supplier countries grouped by region, coloured with the route encoding (open, detour,
    at risk, not sourceable); regions in neutral grey."""
    routes = exposure.by_country(view.routes.assign(exposed=view.exposed), "exposed")
    blocked = blocked or set()
    states = country_states(view, blocked)
    regions = routes.groupby("exporter_region", as_index=False).agg(qty_t=("qty_t", "sum"))
    # Region codes can equal country codes (IND, CHN), so region ids get a prefix.
    ids = [f"region:{r}" for r in regions["exporter_region"]] + list(routes["exporter_iso3"])
    parents = [""] * len(regions) + [f"region:{r}" for r in routes["exporter_region"]]
    values = list(regions["qty_t"]) + list(routes["qty_t"])
    labels = [theme.region_name(r) for r in regions["exporter_region"]] + [
        f"{name} · {theme.route_label(states[iso3])}" if states[iso3] != theme.ROUTE_OPEN else name
        for name, iso3 in zip(routes["exporter_name"], routes["exporter_iso3"], strict=True)
    ]
    colours = [theme.NEUTRAL] * len(regions) + [
        theme.ROUTE_COLOURS[states[iso3]] for iso3 in routes["exporter_iso3"]
    ]
    share = [v / view.extra_t * 100 for v in values]
    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            customdata=share,
            marker={"colors": colours},
            texttemplate="%{label}<br>%{customdata:.0f} %",
            hovertemplate="%{label}: %{value:,.0f} t (%{customdata:.1f} %)<extra></extra>",
        )
    )
    return charts.base_layout(
        fig, height=420, title="Supplier countries, share of imports from outside Europe"
    )


def update(data: AppData, grade: str = ALL_GRADES, scenario: str = LIVE) -> charts.Outputs:
    view = data.sourcing_for(grade, scenario)
    if view is None or view.routes.empty:
        return (
            [charts.no_data("No imports of this grade from outside Europe.")],
            go.Figure(),
            go.Figure(),
        )
    return (
        charts.tiles(kpi_values(view, data)),
        sankey_figure(view, not_sourceable(view, data)),
        treemap_figure(view, not_sourceable(view, data)),
    )


def register(app: Dash, state: AppState) -> None:
    if state.data.sourcing is None:
        return

    @app.callback(
        Output("src-kpis", "children"),
        Output("src-sankey", "figure"),
        Output("src-treemap", "figure"),
        Input("grade", "value"),
        Input("scenario", "value"),
        Input("data-version", "data"),
    )
    def _update(grade: str, scenario: str, _version: int) -> charts.Outputs:
        return update(state.data, grade, scenario)
