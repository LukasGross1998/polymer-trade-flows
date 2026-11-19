"""Tab "Order planner": landed cost against arrival date, recommendation for a need-by date.

Planning estimates (spec 010; sourced inputs only since spec 015): cost of spec 007 plus the
ship transit time (median time in port at both ends + sea days at the average container ship
speed). No quotes, no sailing schedules, one port per region; no recommendation while sea
freight has no sourced rate.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from ptf.app import charts, fmt, theme
from ptf.app.data import AppData, AppState
from ptf.app.tabs.landed_cost import compute as compute_landed
from ptf.app.tabs.landed_cost import default_basis
from ptf.insights import planner as planner_logic
from ptf.insights.config import LeadTime
from ptf.insights.scenario import LIVE
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
        return charts.no_data("No trade data or sea routes loaded yet.")
    lead = data.sourcing_config.lead_time
    need_by = today() + pd.Timedelta(days=lead.default_need_by_days)
    return html.Div(
        [
            theme.method_panel(
                "Planning estimate, not a quote. Ship transit time = median time in port of "
                "container ships at origin and at the destination (UNCTADstat, 2023; "
                f"{lead.port_days.get(lead.destination_country) or 0:.1f} days in the "
                "Netherlands) + sea days at "
                f"{lead.speed:g} knots (average speed at sea of {lead.vessel_size} TEU container "
                "ships, Fourth IMO GHG Study 2020). Not included because no source gives them: "
                "loading and export clearance, waiting for a sailing, import clearance, "
                "delivery to the warehouse, delays from congestion or storms (shown as flags). "
                "Countries without UNCTAD port data have no arrival date (n/a). Cost as in the "
                "Landed cost tab: with Comext the CIF price already contains sea freight and "
                "insurance to the EU border, so the cheapest origin that arrives in time is "
                "recommended; with the BACI basis there is no sourced freight and no "
                "recommendation.",
            ),
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
                ],
                style=theme.ROW,
            ),
            html.Div(
                [
                    charts.control(
                        "Your days before departure (production, booking)",
                        own_days("pl-before"),
                    ),
                    charts.control("Your days for customs clearance", own_days("pl-customs")),
                    charts.control("Your days for delivery to the plant", own_days("pl-delivery")),
                ],
                style=theme.ROW,
                title="Your own estimates (no free source gives these per country); default 0.",
            ),
            html.Div(id="pl-kpis", style=theme.ROW),
            html.Div(
                [
                    charts.graph("pl-timeline"),
                    html.Div(id="pl-not-drawn", style=theme.SMALL_NOTE),
                ],
                style={**theme.CARD, "marginBottom": "16px"},
            ),
            html.Div(id="pl-table", style={**theme.CARD, "marginBottom": "16px"}),
        ]
    )


def own_days(component_id: str) -> dcc.Input:
    return dcc.Input(
        id=component_id,
        type="number",
        min=0,
        step=1,
        value=0,
        debounce=True,
        style={"width": "90px"},
    )


def compute(
    data: AppData,
    need_by: pd.Timestamp,
    quantity_t: float,
    grade: str = ALL_GRADES,
    scenario: str = LIVE,
    order_date: pd.Timestamp | None = None,
    own_before_days: float = 0.0,
    own_after_days: float = 0.0,
    currency: str = "EUR",
) -> PlannerView | None:
    landed = compute_landed(data, scenario, default_basis(data), grade)
    landed = None if landed is None else landed.in_currency(currency)
    tables = data.route_tables
    if landed is None or landed.table.empty or tables is None:
        return None
    start = order_date if order_date is not None else today()
    return planner_view(
        landed,
        tables,
        data.chokepoints,
        data.sourcing_config,
        congested_regions(data.port_activity, data.monitor_config),
        storm_chokepoints(data.weather, start, data.monitor_config),
        start,
        need_by,
        quantity_t,
        own_before_days,
        own_after_days,
    )


def kpi_values(view: PlannerView) -> list[dict[str, str]]:
    table = view.table
    picks = table[table["recommended"]]
    known = table["on_time"].notna()
    in_time = int((table["on_time"] == True).sum())  # noqa: E712 (None means unknown)
    if not picks.empty:
        pick = picks.iloc[0]
        first = {
            "label": "Recommended origin",
            "value": str(pick["exporter_name"]),
            "tone": theme.GOOD,
            "note": f"arrives {pick['arrival']:%d %b %Y} ({pick['lead_days']:.0f} days)",
        }
    else:
        first = {
            "label": "Recommended origin",
            "value": "none",
            "tone": theme.WARNING,
            "note": "sea freight has no sourced rate"
            if not view.landed.freight_known
            else "no origin known to arrive in time",
        }
    fastest = table[known & table["sourceable"].fillna(True)].sort_values("lead_days")
    values = [first]
    if not fastest.empty:
        row = fastest.iloc[0]
        values.append(
            {
                "label": "Shortest ship transit",
                "value": f"{row['lead_days']:.0f} days",
                "note": f"{row['exporter_name']}, order by {row['latest_order']:%d %b %Y} "
                f"at the latest (incl. your {row['total_days'] - row['lead_days']:.0f} days)",
            }
        )
    values.append(
        {
            "label": "Suppliers in time",
            "value": f"{in_time} of {len(table)}",
            "note": f"needed by {view.need_by:%d %b %Y}; "
            f"{int(table['at_risk'].sum())} at risk, "
            f"{int((~known & ~table['at_risk']).sum())} without port data (n/a)",
        }
    )
    payload = view.payload_label
    containers = table["containers"].iloc[0] if "containers" in table and len(table) else None
    values.append(
        {
            "label": "40-foot containers",
            "value": "n/a" if containers is None or pd.isna(containers) else f"≥ {containers:.0f}",
            "note": f"{view.quantity_t:,.0f} t at the maximum payload per box"
            + (f" ({payload})" if payload else "")
            + "; a lower bound",
        }
    )
    return values


def timeline_figure(view: PlannerView, lead: LeadTime) -> go.Figure:
    """One row per origin (spec 018): your days before departure, the ship transit with a band
    from the fastest to the slowest container ship size (IMO table), your days after arrival;
    the need-by date as a line, the cost per tonne in the row label. Origins at risk, not
    sourceable or without a transit time are listed below the chart instead."""
    table = planner_logic.with_transit_range(view.table, lead)
    drawn = table[
        table["arrival"].notna() & ~table["at_risk"] & table["sourceable"].fillna(True)
    ].sort_values("at_site")
    unit = f"{view.landed.currency}/t"
    labels = [
        f"{r['exporter_name']} · {fmt.number(r['landed_eur_t'])} {unit}"
        for r in drawn.to_dict("records")
    ]
    fig = go.Figure()

    def segment(
        name: str,
        starts: list[pd.Timestamp],
        ends: list[pd.Timestamp],
        colour: str,
        width: int,
        show: bool,
    ) -> None:
        for k, (label, a, b) in enumerate(zip(labels, starts, ends, strict=True)):
            fig.add_trace(
                go.Scatter(
                    x=[a, b],
                    y=[label, label],
                    mode="lines",
                    line={"color": colour, "width": width},
                    name=name,
                    legendgroup=name,
                    showlegend=show and k == 0,
                    hovertemplate=f"{name}: %{{x|%d %b %Y}}<extra>{label}</extra>",
                )
            )

    order = view.order_date
    rows = drawn.to_dict("records")
    departure = [r["arrival"] - pd.Timedelta(days=round(r["lead_days"])) for r in rows]
    segment("Your days before departure", [order] * len(rows), departure, theme.GRID, 10, True)
    segment(
        "Transit range (fastest–slowest ship size)",
        [r["arrival_early"] for r in rows],
        [r["arrival_late"] for r in rows],
        theme.with_alpha(theme.BLUE, 0.25),
        16,
        True,
    )
    segment("Ship transit", departure, [r["arrival"] for r in rows], theme.BLUE, 6, True)
    segment(
        "Your days after arrival",
        [r["arrival"] for r in rows],
        [r["at_site"] for r in rows],
        theme.AQUA,
        6,
        True,
    )
    fig.add_vline(
        x=view.need_by.timestamp() * 1000,
        line={"color": theme.INK, "width": 1.5, "dash": "dash"},
        annotation_text="needed by",
        annotation_position="top",
    )
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(labels)))
    fig.update_layout(hovermode="closest")
    return charts.base_layout(
        fig,
        height=max(260, 44 * len(labels) + 120),
        title="From order to arrival, if ordered today (one row per origin)",
    )


def not_drawn(view: PlannerView) -> str:
    """The origins left out of the timeline, with the reason."""
    table = view.table
    parts = []
    for r in table.to_dict("records"):
        if not bool(r.get("sourceable", True)):
            parts.append(f"{r['exporter_name']} (not sourceable)")
        elif r.get("at_risk"):
            parts.append(f"{r['exporter_name']} (at risk)")
        elif pd.isna(r["arrival"]):
            parts.append(f"{r['exporter_name']} (no transit time)")
    return "Not in the timeline: " + ", ".join(parts) if parts else ""


def plan_table(view: PlannerView) -> html.Table:
    unit = f"{view.landed.currency}/t"
    cost = unit if view.landed.freight_known else f"{unit} excl. freight"
    header = [
        "Country",
        cost,
        "Port days",
        "Sea days",
        "Transit days",
        "Ship arrives",
        "Order by",
        "On time",
    ]
    cell = {"padding": "4px 8px", "fontSize": "13px", "textAlign": "right"}
    rows = [html.Tr([html.Th(h, style={**cell, "color": theme.MUTED}) for h in header])]
    for r in view.table.to_dict("records"):
        flags = []
        if r["congested"]:
            flags.append("port below normal")
        if r["storm_on_route"]:
            flags.append("storm on route")
        if r.get("delayed"):
            flags.append("detour")
        if r.get("reduced"):
            flags.append("reduced traffic")
        known = not pd.isna(r["lead_days"])
        port = (
            f"{r['origin_port_days']:.1f} + {r['destination_port_days']:.1f}"
            if known
            else "n/a (no UNCTAD data)"
        )
        usable = bool(r.get("sourceable", True))
        if not usable:
            ok, colour = "not sourceable", theme.MUTED
        elif r.get("at_risk"):
            ok, colour = "⚠ at risk", theme.CRITICAL
        elif r["on_time"] is None:
            ok, colour = "n/a", theme.MUTED
        elif r["on_time"]:
            ok, colour = "● yes", theme.GOOD
        else:
            ok, colour = "✕ late", theme.MUTED
        values = [
            f"{r['landed_eur_t']:,.0f}",
            port,
            f"{r['sea_days']:.1f}",
            (f"{r['lead_days']:.0f}" if known else "n/a")
            + (f" ({', '.join(flags)})" if flags else ""),
            f"{r['arrival']:%d %b}" if known else "n/a",
            f"{r['latest_order']:%d %b}" if known else "n/a",
        ]
        weight = "600" if r["recommended"] else "400"
        rows.append(
            html.Tr(
                [
                    html.Td(
                        r["exporter_name"],
                        title=r.get("sourceable_reason") or "",
                        style={
                            **cell,
                            "textAlign": "left",
                            "fontWeight": weight,
                            "color": theme.INK if usable else theme.MUTED,
                        },
                    )
                ]
                + [
                    html.Td(v, style={**cell, "color": theme.INK if usable else theme.MUTED})
                    for v in values
                ]
                + [html.Td(ok, style={**cell, "color": colour})]
            )
        )
    return html.Table(rows, style={"borderCollapse": "collapse", "width": "100%"})


def update(
    data: AppData,
    need_by: str | pd.Timestamp,
    quantity_t: float | None,
    grade: str = ALL_GRADES,
    scenario: str = LIVE,
    order_date: pd.Timestamp | None = None,
    own_before_days: float | None = 0.0,
    own_after_days: float | None = 0.0,
    currency: str = "EUR",
) -> charts.Outputs:
    quantity = (
        float(quantity_t) if quantity_t else data.sourcing_config.lead_time.default_quantity_t
    )
    view = compute(
        data,
        pd.Timestamp(need_by),
        quantity,
        grade,
        scenario,
        order_date,
        float(own_before_days or 0),
        float(own_after_days or 0),
        currency,
    )
    if view is None:
        return [], go.Figure(), "", charts.no_data("No suppliers with a sea route for this grade.")
    lead = data.sourcing_config.lead_time
    return (
        charts.tiles(kpi_values(view)),
        timeline_figure(view, lead),
        not_drawn(view),
        plan_table(view),
    )


def register(app: Dash, state: AppState) -> None:
    if state.data.import_sources is None or state.data.distances is None:
        return

    @app.callback(
        Output("pl-kpis", "children"),
        Output("pl-timeline", "figure"),
        Output("pl-not-drawn", "children"),
        Output("pl-table", "children"),
        Input("pl-need-by", "date"),
        Input("pl-quantity", "value"),
        Input("grade", "value"),
        Input("scenario", "value"),
        Input("pl-before", "value"),
        Input("pl-customs", "value"),
        Input("pl-delivery", "value"),
        Input("currency", "value"),
        Input("data-version", "data"),
    )
    def _update(
        need_by: str,
        quantity: float | None,
        grade: str,
        scenario: str,
        before: float | None,
        customs: float | None,
        delivery: float | None,
        currency: str,
        _version: int,
    ) -> charts.Outputs:
        after = float(customs or 0) + float(delivery or 0)
        return update(state.data, need_by, quantity, grade, scenario, None, before, after, currency)
