"""Tab "Overview": the current situation on one page."""

import pandas as pd
from dash import Dash, Input, Output, html

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.app.tabs.markets import kpi_values
from ptf.clean.portwatch import EVENT_TYPES
from ptf.monitor.metrics import latest_status, monitor_table, port_table
from ptf.monitor.overview import active_events, disrupted_count, furthest_below_normal


def layout(data: AppData) -> html.Div:
    card = {**style.CARD, "flex": "1", "minWidth": "300px"}
    return html.Div(
        [
            html.Div(id="ov-kpis", style=style.ROW),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                "Chokepoints furthest below normal (all vessels)",
                                style=style.SECTION_TITLE,
                            ),
                            html.Div(id="ov-chokepoints"),
                        ],
                        style=card,
                    ),
                    html.Div(
                        [
                            html.Div(
                                "Ports furthest below normal (port calls)",
                                style=style.SECTION_TITLE,
                            ),
                            html.Div(id="ov-ports"),
                        ],
                        style=card,
                    ),
                ],
                style=style.ROW,
            ),
            html.Div(
                [
                    html.Div(
                        "Active disruption events (IMF PortWatch, orange and red alerts)",
                        style=style.SECTION_TITLE,
                    ),
                    html.Div(id="ov-events"),
                ],
                style=style.CARD,
            ),
        ]
    )


def _location_list(rows: pd.DataFrame) -> html.Div:
    if rows.empty:
        return html.Div("● None flagged", style={"color": style.GOOD})
    items = [
        html.Li(
            [
                html.Span(f"▼ {row.location}", style={"color": style.CRITICAL}),
                f"  {row.deviation_pct:+.0f} % vs. normal",
            ],
            style={"fontSize": "14px", "marginBottom": "4px"},
        )
        for row in rows.itertuples()
    ]
    return html.Ul(items, style={"paddingLeft": "18px", "margin": "0"})


def _event_list(events: pd.DataFrame) -> html.Div:
    if events.empty:
        return html.Div("● No active orange or red alerts", style={"color": style.GOOD})
    items = []
    for event in events.itertuples():
        kind = EVENT_TYPES.get(event.event_type, event.event_type)
        since = f"since {event.from_date:%d %b %Y}" + (
            "" if pd.isna(event.to_date) else f", until {event.to_date:%d %b %Y}"
        )
        items.append(
            html.Li(
                [
                    html.Span(
                        f"▲ {event.alert_level} ",
                        style={"color": style.CRITICAL, "fontWeight": "600"},
                    ),
                    f"{event.event} ({kind}), {since}",
                ],
                style={"fontSize": "14px", "marginBottom": "4px"},
            )
        )
    return html.Ul(items, style={"paddingLeft": "18px", "margin": "0"})


def update(data: AppData) -> tuple:
    chokepoints = latest_status(monitor_table(data.transits, "total", data.monitor_config))
    flagged, total = disrupted_count(chokepoints)
    values = [
        {
            "label": "Chokepoints disrupted (all vessels)",
            "value": f"{flagged} of {total}",
            "tone": style.CRITICAL if flagged else style.GOOD,
            "note": f"data up to {data.latest_date:%d %b %Y}",
        }
    ]
    if data.market is not None:
        values += kpi_values(data.market)[:3]  # Brent, gas spread, GSCPI

    if data.port_activity is not None:
        ports = latest_status(port_table(data.port_activity, "portcalls", data.monitor_config))
        port_list = _location_list(furthest_below_normal(ports))
    else:
        port_list = html.Div("No port data yet.", style={"color": style.MUTED})

    events = html.Div("No event data yet.", style={"color": style.MUTED})
    if data.events is not None:
        events = _event_list(active_events(data.events, data.latest_date))

    return (
        charts.tiles(values),
        _location_list(furthest_below_normal(chokepoints)),
        port_list,
        events,
    )


def register(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("ov-kpis", "children"),
        Output("ov-chokepoints", "children"),
        Output("ov-ports", "children"),
        Output("ov-events", "children"),
        Input("data-version", "data"),
    )
    def _update(_version: int) -> tuple:
        return update(state.data)
