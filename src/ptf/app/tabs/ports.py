"""Tab "Ports": port calls and estimated trade volumes of polyethylene-relevant ports."""

from typing import Any

import pandas as pd
from dash import Dash, Input, Output, dcc, html, no_update

from ptf.app import charts, theme, weather_card
from ptf.app.data import AppData, AppState, require
from ptf.shipping.metrics import latest_status, port_table
from ptf.shipping.overview import active_events
from ptf.shipping.vocabulary import PORT_METRICS

# Volumes are tonnes per day; counts are vessels per day.
UNITS = {"import": "t per day", "export": "t per day"}
DEFAULT_PORT = "port24"  # Jubail: Saudi petrochemical port inside the Strait of Hormuz


def _unit(metric: str) -> str:
    return UNITS.get(metric, "vessels per day")


def layout(data: AppData) -> html.Div:
    if data.port_activity is None or data.ports is None:
        return charts.no_data("No port data loaded yet – use Update data.")
    options = [{"label": f"{p.name} ({p.role})", "value": p.id} for p in data.monitor_config.ports]
    controls = html.Div(
        [
            charts.control(
                "Port (or click on the map)",
                dcc.Dropdown(
                    id="port-select", options=options, value=DEFAULT_PORT, clearable=False
                ),
            ),
            charts.control(
                "Metric",
                dcc.Dropdown(
                    id="port-metric",
                    options=[
                        {"label": v.capitalize(), "value": k} for k, v in PORT_METRICS.items()
                    ],
                    value="export",
                    clearable=False,
                ),
            ),
            charts.control("Period", charts.period_dropdown("port-period")),
            charts.control("Map", charts.seamark_switch("port-seamarks")),
        ],
        style=theme.ROW,
    )
    return html.Div(
        [
            theme.method_panel(
                "Source: IMF PortWatch. Port calls are counted from satellite AIS data; import and "
                "export volumes are PortWatch estimates from vessel draught and capacity, not "
                "customs statistics. Normal = same calendar week in 2019-2023.",
            ),
            controls,
            html.Div(id="port-kpis", style=theme.ROW),
            html.Div(
                [
                    html.Div(
                        charts.graph("port-map"),
                        style={**theme.CARD, "flex": "1", "minWidth": "420px"},
                    ),
                    html.Div(
                        [
                            html.Div("All ports, latest week", style=theme.SECTION_TITLE),
                            html.Div(id="port-table"),
                        ],
                        style={**theme.CARD, "flex": "1", "minWidth": "320px"},
                    ),
                ],
                style=theme.ROW,
            ),
            html.Div(charts.graph("port-timeseries"), style=theme.CARD),
            weather_card.layout("port-weather", data.monitor_config.weather),
        ]
    )


def status_table(status: pd.DataFrame, unit: str) -> html.Table:
    """Simple HTML table: port, 7-day value, deviation and status (icon + label)."""
    header = html.Tr(
        [
            html.Th(t, style={"textAlign": "left", "fontSize": "12px", "color": theme.MUTED})
            for t in ["Port", f"7-day avg ({unit})", "vs. normal", "Status"]
        ]
    )
    rows = []
    for row in status.sort_values("deviation_pct").to_dict("records"):
        state = charts.status_value(bool(row["is_disrupted"]))
        rows.append(
            html.Tr(
                [
                    html.Td(row["location"]),
                    html.Td(charts.number(row["rolling"], ",.0f")),
                    html.Td(charts.signed_pct(row["deviation_pct"])),
                    html.Td(state["value"], style={"color": state["tone"]}),
                ],
                style={"fontSize": "13px"},
            )
        )
    return html.Table([header, *rows], style={"width": "100%", "borderCollapse": "collapse"})


def update(
    data: AppData, port_id: str, metric: str, period: str, seamarks: bool = False
) -> charts.Outputs:
    unit = _unit(metric)
    label = PORT_METRICS[metric]
    activity = require(data.port_activity, "port_activity")
    table = port_table(activity, metric, data.monitor_config)
    status = latest_status(table)
    row = status[status["location_id"] == port_id].iloc[0]
    latest = activity["date"].max()
    events = None if data.events is None else active_events(data.events, latest)

    map_fig = charts.location_map(
        status, data.port_coordinates(), port_id, unit, events, ",.0f", seamarks
    )
    kpis = charts.tiles(
        [
            {
                "label": f"{label.capitalize()}, 7-day average",
                "value": charts.number(row["rolling"], ",.0f"),
                "note": unit,
            },
            {
                "label": "vs. normal (same week 2019-2023)",
                "value": charts.signed_pct(row["deviation_pct"]),
            },
            {"label": "vs. same week last year", "value": charts.signed_pct(row["yoy_pct"])},
            {"label": "Status", **charts.status_value(bool(row["is_disrupted"]))},
        ]
    )
    selected = charts.filter_period(table[table["location_id"] == port_id], period, latest)
    series_fig = charts.location_timeseries(selected, f"{row['location']}: {label}", unit)
    start = charts.period_start(period, latest, activity["date"].min())
    charts.add_key_events(series_fig, data.market_config.key_events, start, latest)
    return map_fig, kpis, status_table(status, unit), series_fig


def register(app: Dash, state: AppState) -> None:
    if state.data.port_activity is None:
        return

    @app.callback(
        Output("port-map", "figure"),
        Output("port-kpis", "children"),
        Output("port-table", "children"),
        Output("port-timeseries", "figure"),
        Input("port-select", "value"),
        Input("port-metric", "value"),
        Input("port-period", "value"),
        Input("port-seamarks", "value"),
        Input("data-version", "data"),
    )
    def _update(
        port_id: str, metric: str, period: str, seamarks: list[str], _version: int
    ) -> charts.Outputs:
        return update(state.data, port_id, metric, period, bool(seamarks))

    @app.callback(
        Output("port-weather-waves", "figure"),
        Output("port-weather-gusts", "figure"),
        Output("port-weather-note", "children"),
        Input("port-select", "value"),
        Input("data-version", "data"),
    )
    def _weather(port_id: str, _version: int) -> charts.Outputs:
        return weather_card.update(state.data, port_id)

    @app.callback(
        Output("port-select", "value"), Input("port-map", "clickData"), prevent_initial_call=True
    )
    def _select_on_map(click_data: dict[str, Any] | None) -> object:
        point = (click_data or {}).get("points", [{}])[0]
        return point.get("customdata") or no_update
