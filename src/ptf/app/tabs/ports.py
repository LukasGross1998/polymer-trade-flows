"""Tab "Ports": port calls and estimated trade volumes of polyethylene-relevant ports."""

import pandas as pd
from dash import Dash, Input, Output, dcc, html, no_update

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.clean.portwatch import PORT_METRICS
from ptf.monitor.metrics import latest_status, port_table
from ptf.monitor.overview import active_events

# Volumes are tonnes per day; counts are vessels per day.
UNITS = {"import": "t per day", "export": "t per day"}
DEFAULT_PORT = "port24"  # Jubail: Saudi petrochemical port inside the Strait of Hormuz


def _unit(metric: str) -> str:
    return UNITS.get(metric, "vessels per day")


def layout(data: AppData) -> html.Div:
    if data.port_activity is None or data.ports is None:
        return charts.no_data("No port data yet: run `uv run python -m ptf.pipeline portwatch`.")
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
        ],
        style=style.ROW,
    )
    return html.Div(
        [
            controls,
            html.Div(id="port-kpis", style=style.ROW),
            html.Div(
                [
                    html.Div(
                        charts.graph("port-map"),
                        style={**style.CARD, "flex": "1", "minWidth": "420px"},
                    ),
                    html.Div(
                        [
                            html.Div("All ports, latest week", style=style.SECTION_TITLE),
                            html.Div(id="port-table"),
                        ],
                        style={**style.CARD, "flex": "1", "minWidth": "320px"},
                    ),
                ],
                style=style.ROW,
            ),
            html.Div(charts.graph("port-timeseries"), style=style.CARD),
            html.Div(
                "Source: IMF PortWatch. Port calls are counted from satellite AIS data; import and "
                "export volumes are PortWatch estimates from vessel draught and capacity, not "
                "customs statistics. Normal = same calendar week in 2019-2023.",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def status_table(status: pd.DataFrame, unit: str) -> html.Table:
    """Simple HTML table: port, 7-day value, deviation and status (icon + label)."""
    header = html.Tr(
        [
            html.Th(t, style={"textAlign": "left", "fontSize": "12px", "color": style.MUTED})
            for t in ["Port", f"7-day avg ({unit})", "vs. normal", "Status"]
        ]
    )
    rows = []
    for row in status.sort_values("deviation_pct").itertuples():
        state = charts.status_value(bool(row.is_disrupted))
        rows.append(
            html.Tr(
                [
                    html.Td(row.location),
                    html.Td(charts.number(row.rolling, ",.0f")),
                    html.Td(charts.signed_pct(row.deviation_pct)),
                    html.Td(state["value"], style={"color": state["tone"]}),
                ],
                style={"fontSize": "13px"},
            )
        )
    return html.Table([header, *rows], style={"width": "100%", "borderCollapse": "collapse"})


def update(data: AppData, port_id: str, metric: str, period: str) -> tuple:
    unit = _unit(metric)
    label = PORT_METRICS[metric]
    table = port_table(data.port_activity, metric, data.monitor_config)
    status = latest_status(table)
    row = status[status["location_id"] == port_id].iloc[0]
    latest = data.port_activity["date"].max()
    events = None if data.events is None else active_events(data.events, latest)

    map_fig = charts.location_map(status, data.port_coordinates(), port_id, unit, events, ",.0f")
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
    start = charts.period_start(period, latest, data.port_activity["date"].min())
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
        Input("data-version", "data"),
    )
    def _update(port_id: str, metric: str, period: str, _version: int) -> tuple:
        return update(state.data, port_id, metric, period)

    @app.callback(
        Output("port-select", "value"), Input("port-map", "clickData"), prevent_initial_call=True
    )
    def _select_on_map(click_data: dict | None) -> str:
        point = (click_data or {}).get("points", [{}])[0]
        return point.get("customdata") or no_update
