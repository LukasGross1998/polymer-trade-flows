"""Tab "Sourcing": whom does Europe depend on, and which imports pass a disrupted chokepoint?

Combines the BACI import sources with the sea routes and today's chokepoint status
(`ptf.insights`, spec 006).
"""

import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.insights import signals
from ptf.insights.view import ALL_GRADES, SourcingView

EXPOSED_COLOUR = style.RED
SAFE_COLOUR = style.BLUE
LEVEL_TONES = {
    signals.GREEN: style.GOOD,
    signals.YELLOW: style.WARNING,
    signals.ORANGE: style.ELEVATED,
    signals.RED: style.CRITICAL,
}


def layout(data: AppData) -> html.Div:
    if data.sourcing is None:
        return charts.no_data(
            "No sourcing data yet: run `uv run ptf clean` (trade marts) and "
            "`uv run ptf ingest` (sea routes with passages)."
        )
    # Full-width charts: the route labels of the Sankey need the room.
    card = {**style.CARD, "marginBottom": "16px"}
    return html.Div(
        [
            html.Div(charts.control("Grade", grade_dropdown("src-grade", data)), style=style.ROW),
            html.Div(id="src-kpis", style=style.ROW),
            html.Div(charts.graph("src-sankey"), style=card),
            html.Div(charts.graph("src-treemap"), style=card),
            html.Div(
                f"Imports of polyethylene (HS 3901) into Europe from outside the region, CEPII "
                f"BACI {data.sourcing.year} (latest year available). Routes: shortest sea route "
                "from one representative port per region (searoute): every country ships like its "
                "region's port (e.g. all Middle East exports from Jebel Ali), so the exposure is "
                "an approximation. Red = the route passes a chokepoint that the monitor flags as "
                "disrupted today (all vessels, below "
                f"{data.monitor_config.disruption_threshold:.0%} of normal).",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def kpi_values(view: SourcingView, data: AppData) -> list[dict[str, str]]:
    level = signals.level(view.exposure_pct, data.sourcing_config.signals.supply)
    top = view.routes.nlargest(3, "qty_t")["exporter_name"].tolist()
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
            "label": "Through a disrupted chokepoint",
            "value": f"{view.exposure_pct:.0f} %",
            "tone": LEVEL_TONES[level],
            "note": ", ".join(view.disrupted) or "no disrupted chokepoint on the routes",
        },
        {
            "label": "Top-3 supplier countries",
            "value": f"{view.top3_pct:.0f} %",
            "note": ", ".join(top),
        },
    ]


def sankey_figure(view: SourcingView) -> go.Figure:
    """Exporter region -> route -> Europe; links through disrupted chokepoints in red."""
    routes = view.routes.assign(exposed=view.exposed)
    grouped = routes.groupby(["exporter_region", "route", "exposed"], as_index=False)
    by_route = grouped.agg(qty_t=("qty_t", "sum")).sort_values("qty_t", ascending=False)
    regions = list(dict.fromkeys(by_route["exporter_region"]))
    route_names = list(dict.fromkeys(by_route["route"]))
    labels = regions + route_names + ["Europe"]
    index = {name: i for i, name in enumerate(labels)}

    def colour(exposed: bool) -> str:
        return "rgba(227, 73, 72, 0.45)" if exposed else "rgba(137, 135, 129, 0.30)"

    source, target, value, colours = [], [], [], []
    for row in by_route.to_dict("records"):
        source.append(index[row["exporter_region"]])
        target.append(index[row["route"]])
        value.append(row["qty_t"] / 1e3)
        colours.append(colour(bool(row["exposed"])))
    to_europe = by_route.groupby(["route", "exposed"], as_index=False).agg(qty_t=("qty_t", "sum"))
    for row in to_europe.to_dict("records"):
        source.append(index[row["route"]])
        target.append(index["Europe"])
        value.append(row["qty_t"] / 1e3)
        colours.append(colour(bool(row["exposed"])))

    fig = go.Figure(
        go.Sankey(
            node={
                "label": labels,
                "pad": 14,
                "thickness": 14,
                "color": style.INK_SECONDARY,
                "line": {"width": 0},
            },
            link={
                "source": source,
                "target": target,
                "value": value,
                "color": colours,
                "hovertemplate": (
                    "%{source.label} → %{target.label}: %{value:,.0f} kt<extra></extra>"
                ),
            },
        )
    )
    return charts.base_layout(
        fig, height=460, title="Import routes into Europe: region → sea route → Europe (kt)"
    )


def treemap_figure(view: SourcingView) -> go.Figure:
    """Supplier countries grouped by region; red = route passes a disrupted chokepoint."""
    routes = view.routes.assign(exposed=view.exposed)
    regions = routes.groupby("exporter_region", as_index=False).agg(
        qty_t=("qty_t", "sum"), exposed=("exposed", "max")
    )
    # Region codes can equal country codes (IND, CHN), so region ids get a prefix.
    ids = [f"region:{r}" for r in regions["exporter_region"]] + list(routes["exporter_iso3"])
    labels = list(regions["exporter_region"]) + list(routes["exporter_name"])
    parents = [""] * len(regions) + [f"region:{r}" for r in routes["exporter_region"]]
    values = list(regions["qty_t"]) + list(routes["qty_t"])
    flags = list(regions["exposed"]) + list(routes["exposed"])
    share = [v / view.extra_t * 100 for v in values]
    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            customdata=share,
            marker={"colors": [EXPOSED_COLOUR if f else SAFE_COLOUR for f in flags]},
            texttemplate="%{label}<br>%{customdata:.0f} %",
            hovertemplate="%{label}: %{value:,.0f} t (%{customdata:.1f} %)<extra></extra>",
        )
    )
    return charts.base_layout(
        fig, height=420, title="Supplier countries, share of imports from outside Europe"
    )


def grade_dropdown(component_id: str, data: AppData) -> dcc.Dropdown:
    """PE grade filter (spec 008), shared with the landed-cost tab."""
    return dcc.Dropdown(
        id=component_id, options=data.grade_options(), value=ALL_GRADES, clearable=False
    )


def update(data: AppData, grade: str = ALL_GRADES) -> charts.Outputs:
    view = data.sourcing_for(grade)
    if view is None or view.routes.empty:
        return (
            [charts.no_data("No imports of this grade from outside Europe.")],
            go.Figure(),
            go.Figure(),
        )
    return (
        charts.tiles(kpi_values(view, data)),
        sankey_figure(view),
        treemap_figure(view),
    )


def register(app: Dash, state: AppState) -> None:
    if state.data.sourcing is None:
        return

    @app.callback(
        Output("src-kpis", "children"),
        Output("src-sankey", "figure"),
        Output("src-treemap", "figure"),
        Input("src-grade", "value"),
        Input("data-version", "data"),
    )
    def _update(grade: str, _version: int) -> charts.Outputs:
        return update(state.data, grade)
