"""Tab "Chokepoints": vessel transits through maritime chokepoints vs. normal."""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, no_update
from plotly.subplots import make_subplots

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.monitor.metrics import diversion_ratio, latest_status, monitor_table
from ptf.monitor.overview import active_events

VESSEL_LABELS = {
    "total": "all vessels",
    "container": "container ships",
    "tanker": "tankers",
    "dry_bulk": "dry bulk carriers",
    "general_cargo": "general cargo ships",
    "roro": "RoRo ships",
}
DEFAULT_CHOKEPOINT = "chokepoint4"  # Bab el-Mandeb: the Red Sea crisis is the reference case


def layout(data: AppData) -> html.Div:
    options = [
        {"label": row.chokepoint, "value": row.chokepoint_id}
        for row in data.chokepoints.sort_values("chokepoint").itertuples()
    ]
    controls = html.Div(
        [
            charts.control(
                "Chokepoint (or click on the map)",
                dcc.Dropdown(
                    id="cp-select", options=options, value=DEFAULT_CHOKEPOINT, clearable=False
                ),
            ),
            charts.control(
                "Vessel type",
                dcc.Dropdown(
                    id="cp-vessel-type",
                    options=[
                        {"label": v.capitalize(), "value": k} for k, v in VESSEL_LABELS.items()
                    ],
                    value="container",
                    clearable=False,
                ),
            ),
            charts.control("Period", charts.period_dropdown("cp-period")),
        ],
        style=style.ROW,
    )
    return html.Div(
        [
            controls,
            html.Div(id="cp-kpis", style=style.ROW),
            html.Div(charts.graph("cp-map"), style=style.CARD),
            html.Div(
                [
                    html.Div(
                        charts.graph("cp-timeseries"),
                        style={**style.CARD, "flex": "1", "minWidth": "420px"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                "Red Sea diversion: container ships between Asia and Europe",
                                style=style.SECTION_TITLE,
                            ),
                            charts.graph("cp-diversion"),
                        ],
                        style={**style.CARD, "flex": "1", "minWidth": "420px"},
                    ),
                ],
                style={**style.ROW, "marginTop": "16px"},
            ),
            html.Div(
                "Source: IMF PortWatch (daily transit counts from satellite AIS data). Not "
                "real-time: data arrive a few days late and are updated about weekly. Normal = "
                "average of the same calendar week in 2019-2023. Chokepoints with less than 2 "
                "vessels a day of normal traffic are never flagged. AIS counts also drop when "
                "ships switch off their transponders.",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def diversion_figure(
    ratio: pd.DataFrame, key_events: list, start: pd.Timestamp, end: pd.Timestamp
) -> go.Figure:
    """Red Sea vs. Cape route for container ships, and the Cape share below (no dual axis)."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.62, 0.38],
        vertical_spacing=0.08,
        subplot_titles=("Container ships per day (7-day average)", "Share taking the Cape route"),
    )
    for name, column, colour in [
        ("Bab el-Mandeb (Red Sea)", "red_sea_rolling", style.BLUE),
        ("Cape of Good Hope", "cape_rolling", style.ORANGE),
    ]:
        fig.add_trace(
            go.Scatter(
                x=ratio["date"],
                y=ratio[column],
                line={"color": colour, "width": 2},
                name=name,
                hovertemplate="%{y:.1f}",
            ),
            row=1,
            col=1,
        )
    fig.add_trace(
        go.Scatter(
            x=ratio["date"],
            y=ratio["cape_share"] * 100,
            line={"color": style.INK_SECONDARY, "width": 2},
            name="Cape share",
            showlegend=False,
            hovertemplate="%{y:.0f} %",
        ),
        row=2,
        col=1,
    )
    fig.update_yaxes(rangemode="tozero", row=1, col=1)
    fig.update_yaxes(range=[0, 100], ticksuffix=" %", row=2, col=1)
    fig.update_annotations(font={"color": style.INK, "size": 13})
    charts.add_key_events(fig, key_events, start, end)
    return charts.base_layout(fig, height=460)


def update(data: AppData, chokepoint_id: str, vessel_type: str, period: str) -> tuple:
    """Map, tiles, time series and diversion chart for the current selection."""
    label = VESSEL_LABELS[vessel_type]
    table = monitor_table(data.transits, vessel_type, data.monitor_config)
    status = latest_status(table)
    selected = table[table["location_id"] == chokepoint_id]
    row = status[status["location_id"] == chokepoint_id].iloc[0]
    events = None if data.events is None else active_events(data.events, data.latest_date)

    map_fig = charts.location_map(
        status, data.chokepoint_coordinates(), chokepoint_id, f"{label} per day", events
    )
    kpis = charts.tiles(
        [
            {
                "label": f"{label.capitalize()} per day, last 7 days",
                "value": charts.number(row["rolling"]),
            },
            {
                "label": "vs. normal (same week 2019-2023)",
                "value": charts.signed_pct(row["deviation_pct"]),
            },
            {"label": "vs. same week last year", "value": charts.signed_pct(row["yoy_pct"])},
            {"label": "Status", **charts.status_value(bool(row["is_disrupted"]))},
        ]
    )
    start = charts.period_start(period, data.latest_date, data.transits["date"].min())
    key_events = data.market_config.key_events
    series_fig = charts.location_timeseries(
        charts.filter_period(selected, period, data.latest_date),
        f"{row['location']}: {label} per day",
        f"{label} per day",
    )
    charts.add_key_events(series_fig, key_events, start, data.latest_date)
    ratio = charts.filter_period(
        diversion_ratio(data.transits, data.monitor_config), period, data.latest_date
    )
    return map_fig, kpis, series_fig, diversion_figure(ratio, key_events, start, data.latest_date)


def register(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("cp-map", "figure"),
        Output("cp-kpis", "children"),
        Output("cp-timeseries", "figure"),
        Output("cp-diversion", "figure"),
        Input("cp-select", "value"),
        Input("cp-vessel-type", "value"),
        Input("cp-period", "value"),
        Input("data-version", "data"),  # changes after "Update data" -> redraw
    )
    def _update(chokepoint_id: str, vessel_type: str, period: str, _version: int) -> tuple:
        return update(state.data, chokepoint_id, vessel_type, period)

    @app.callback(
        Output("cp-select", "value"), Input("cp-map", "clickData"), prevent_initial_call=True
    )
    def _select_on_map(click_data: dict | None) -> str:
        point = (click_data or {}).get("points", [{}])[0]
        return point.get("customdata") or no_update  # clicks on event crosses have no id
