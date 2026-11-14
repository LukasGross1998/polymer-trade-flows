"""Tab "Order planner": landed cost against arrival date, recommendation for a need-by date.

Planning estimates (spec 010): landed cost of spec 007 plus lead times from sea distances,
port and weather buffers. No real quotes, average transit times, one port per region.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.app.tabs.landed_cost import compute as compute_landed
from ptf.app.tabs.landed_cost import radio
from ptf.app.tabs.sourcing import grade_dropdown
from ptf.insights.view import (
    ALL_GRADES,
    PlannerView,
    congested_regions,
    planner_view,
    storm_chokepoints,
)


def today() -> pd.Timestamp:
    return pd.Timestamp(pd.Timestamp.now(tz="UTC").date())


def layout(data: AppData) -> html.Div:
    if data.import_sources is None or data.distances is None:
        return charts.no_data(
            "No planner data yet: run `uv run ptf clean` and `uv run ptf ingest`."
        )
    lead = data.sourcing_config.lead_time
    need_by = today() + pd.Timedelta(days=lead.default_need_by_days)
    route_options = [{"label": "Red Sea open", "value": "open"}]
    if data.distances_closed is not None:
        route_options.append({"label": "Red Sea closed", "value": "closed"})
    return html.Div(
        [
            html.Div(
                [
                    charts.control(
                        "Needed by",
                        dcc.DatePickerSingle(
                            id="pl-need-by",
                            date=f"{need_by:%Y-%m-%d}",
                            display_format="DD MMM YYYY",
                        ),
                    ),
                    charts.control(
                        "Quantity (t)",
                        dcc.Input(
                            id="pl-quantity",
                            type="number",
                            min=1,
                            step=25,
                            value=lead.default_quantity_t,
                            style={"width": "120px"},
                        ),
                    ),
                    charts.control("Grade", grade_dropdown("pl-grade", data)),
                    charts.control("Route", radio("pl-route", route_options, "open")),
                ],
                style=style.ROW,
            ),
            html.Div(id="pl-kpis", style=style.ROW),
            html.Div(charts.graph("pl-scatter"), style={**style.CARD, "marginBottom": "16px"}),
            html.Div(id="pl-table", style={**style.CARD, "marginBottom": "16px"}),
            html.Div(
                f"Planning estimate, not a quote. Lead time = {lead.origin_port_days:g} days at "
                f"the origin port + sea days at {lead.speed_knots:g} knots + "
                f"{lead.destination_port_days:g} days at the destination, plus "
                f"{lead.congestion_buffer_days:g} days if a monitored port of the region is below "
                f"normal and {lead.storm_buffer_days:g} days if a chokepoint on the route has a "
                "storm forecast, plus days overland for landlocked exporters "
                "(config/sourcing.yaml). "
                "Landed cost as in the Landed cost tab "
                "(BACI prices, LP freight assumption, EU duty). One port per region, average "
                "transit times, no sailing schedules. Buy in Europe: average price within "
                f"Europe, {lead.europe_days:g} days.",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def compute(
    data: AppData,
    need_by: pd.Timestamp,
    quantity_t: float,
    grade: str = ALL_GRADES,
    route: str = "open",
    order_date: pd.Timestamp | None = None,
) -> PlannerView | None:
    landed = compute_landed(data, route, 1.0, "baci", grade)
    if landed is None or landed.table.empty or data.distances is None:
        return None
    closed = route == "closed" and data.distances_closed is not None
    distances = data.distances_closed if closed else data.distances
    assert distances is not None
    start = order_date if order_date is not None else today()
    return planner_view(
        landed,
        distances,
        data.chokepoints,
        data.sourcing_config,
        congested_regions(data.port_activity, data.monitor_config),
        storm_chokepoints(data.weather, start, data.monitor_config),
        start,
        need_by,
        quantity_t,
    )


def kpi_values(view: PlannerView) -> list[dict[str, str]]:
    table = view.table
    pick = table[table["recommended"]].iloc[0]
    reference = view.landed.reference_eur_t
    on_time = bool(pick["on_time"])
    values = [
        {
            "label": "Recommended origin" if on_time else "No origin in time – earliest",
            "value": str(pick["exporter_name"]),
            "tone": style.GOOD if on_time else style.WARNING,
            "note": f"arrives {pick['arrival']:%d %b %Y} ({pick['lead_days']:.0f} days)",
        },
        {
            "label": "Landed cost",
            "value": f"{pick['landed_eur_t']:,.0f} EUR/t",
            "note": f"{pick['total_eur'] / 1e3:,.0f} thousand EUR for {view.quantity_t:,.0f} t",
        },
    ]
    if reference is not None:
        diff = (pick["landed_eur_t"] - reference) * view.quantity_t
        values.append(
            {
                "label": "vs. buying in Europe",
                "value": f"{diff / 1e3:+,.0f} thousand EUR",
                "note": f"{reference:,.0f} EUR/t, arrives {view.europe_arrival:%d %b}",
            }
        )
    values.append(
        {
            "label": "Suppliers in time",
            "value": f"{int(table['on_time'].sum())} of {len(table)}",
            "note": f"needed by {view.need_by:%d %b %Y}",
        }
    )
    return values


def scatter_figure(view: PlannerView) -> go.Figure:
    table = view.table
    size = 10 + 30 * (table["qty_t"] / table["qty_t"].max()) ** 0.5
    colours = [
        style.ORANGE if rec else (style.BLUE if ok else style.MUTED)
        for rec, ok in zip(table["recommended"], table["on_time"], strict=True)
    ]
    hover = [
        f"<b>{r['exporter_name']}</b><br>{r['landed_eur_t']:,.0f} EUR/t<br>"
        f"arrives {r['arrival']:%d %b} ({r['lead_days']:.0f} days)"
        + ("<br>route through a disrupted chokepoint" if r.get("exposed") else "")
        + ("<br>storm on the route" if r["storm_on_route"] else "")
        + ("<br>port below normal" if r["congested"] else "")
        for r in table.to_dict("records")
    ]
    fig = go.Figure(
        go.Scatter(
            x=table["arrival"],
            y=table["landed_eur_t"],
            mode="markers+text",
            text=table["exporter_name"],
            textposition="top center",
            hovertext=hover,
            hoverinfo="text",
            marker={"size": size, "color": colours, "line": {"color": style.SURFACE, "width": 2}},
            showlegend=False,
        )
    )
    reference = view.landed.reference_eur_t
    if reference is not None:
        fig.add_trace(
            go.Scatter(
                x=[view.europe_arrival],
                y=[reference],
                mode="markers+text",
                text=["Buy in Europe"],
                textposition="bottom center",
                marker={"size": 12, "symbol": "diamond", "color": style.INK_SECONDARY},
                hovertemplate="Buy in Europe: %{y:,.0f} EUR/t<extra></extra>",
                showlegend=False,
            )
        )
    fig.add_vline(
        x=view.need_by.timestamp() * 1000,
        line={"color": style.CRITICAL, "width": 1.5, "dash": "dash"},
        annotation_text="needed by",
        annotation_position="top",
    )
    fig.update_yaxes(title={"text": "EUR per tonne, delivered", "font": {"color": style.MUTED}})
    fig.update_layout(hovermode="closest")
    return charts.base_layout(
        fig,
        height=460,
        title="Landed cost vs. arrival date if ordered today (orange = recommended)",
    )


def plan_table(view: PlannerView) -> html.Table:
    header = [
        "Country",
        "Landed EUR/t",
        "Sea days",
        "Extra days",
        "Lead days",
        "Arrival",
        "On time",
    ]
    cell = {"padding": "4px 8px", "fontSize": "13px", "textAlign": "right"}
    rows = [html.Tr([html.Th(h, style={**cell, "color": style.MUTED}) for h in header])]
    for r in view.table.to_dict("records"):
        flags = []
        if r["congested"]:
            flags.append("port below normal")
        if r["storm_on_route"]:
            flags.append("storm")
        if r["overland_days"]:
            flags.append(f"{r['overland_days']:.0f} days overland")
        extra = r["buffer_days"] + r["overland_days"]
        buffer = f"{extra:.0f}" + (f" ({', '.join(flags)})" if flags else "")
        ok = "● yes" if r["on_time"] else "✕ late"
        values = [
            f"{r['landed_eur_t']:,.0f}",
            f"{r['sea_days']:.1f}",
            buffer,
            f"{r['lead_days']:.0f}",
            f"{r['arrival']:%d %b}",
        ]
        weight = "600" if r["recommended"] else "400"
        rows.append(
            html.Tr(
                [
                    html.Td(
                        r["exporter_name"],
                        style={**cell, "textAlign": "left", "fontWeight": weight},
                    )
                ]
                + [html.Td(v, style=cell) for v in values]
                + [
                    html.Td(
                        ok, style={**cell, "color": style.GOOD if r["on_time"] else style.MUTED}
                    )
                ]
            )
        )
    return html.Table(rows, style={"borderCollapse": "collapse", "width": "100%"})


def update(
    data: AppData,
    need_by: str | pd.Timestamp,
    quantity_t: float | None,
    grade: str = ALL_GRADES,
    route: str = "open",
    order_date: pd.Timestamp | None = None,
) -> charts.Outputs:
    quantity = (
        float(quantity_t) if quantity_t else data.sourcing_config.lead_time.default_quantity_t
    )
    view = compute(data, pd.Timestamp(need_by), quantity, grade, route, order_date)
    if view is None:
        return [], go.Figure(), charts.no_data("No suppliers with a sea route for this grade.")
    return charts.tiles(kpi_values(view)), scatter_figure(view), plan_table(view)


def register(app: Dash, state: AppState) -> None:
    if state.data.import_sources is None or state.data.distances is None:
        return

    @app.callback(
        Output("pl-kpis", "children"),
        Output("pl-scatter", "figure"),
        Output("pl-table", "children"),
        Input("pl-need-by", "date"),
        Input("pl-quantity", "value"),
        Input("pl-grade", "value"),
        Input("pl-route", "value"),
        Input("data-version", "data"),
    )
    def _update(
        need_by: str, quantity: float | None, grade: str, route: str, _version: int
    ) -> charts.Outputs:
        return update(state.data, need_by, quantity, grade, route)
