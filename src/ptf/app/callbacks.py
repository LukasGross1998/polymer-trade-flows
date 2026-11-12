"""Dash callbacks: connect user input to `ptf.monitor` and `ptf.app.figures`.

How a callback works: the decorator names the Inputs (component id + property). Whenever one
of them changes in the browser, Dash calls the function with the new values and writes its
return values into the Outputs. The functions below only pass values through to `src/ptf`
functions, so `update_views` can be tested like any other Python function.
"""

from dash import Dash, Input, Output, State, no_update

from ptf.app import figures
from ptf.app.data import AppState, MonitorData
from ptf.app.layout import kpi_tiles
from ptf.monitor.metrics import diversion_ratio, latest_status, monitor_table


def update_views(data: MonitorData, chokepoint_id: str, vessel_type: str, period: str) -> tuple:
    """Everything that depends on the three controls: map, tiles, both charts, freshness."""
    table = monitor_table(data.transits, vessel_type, data.config)
    status = latest_status(table)
    selected = table[table["chokepoint_id"] == chokepoint_id]
    selected_status = status[status["chokepoint_id"] == chokepoint_id].iloc[0]

    map_fig = figures.map_figure(status, data.chokepoints, chokepoint_id, vessel_type)
    tiles = kpi_tiles(figures.kpis(selected_status, vessel_type))
    series_fig = figures.timeseries_figure(
        figures.filter_period(selected, period, data.latest_date),
        selected_status["chokepoint"],
        vessel_type,
    )
    ratio = figures.filter_period(
        diversion_ratio(data.transits, data.config), period, data.latest_date
    )
    diversion_fig = figures.diversion_figure(ratio)
    freshness = f"Data up to {data.latest_date:%d %b %Y} · IMF PortWatch"
    return map_fig, tiles, series_fig, diversion_fig, freshness


def register_callbacks(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("map", "figure"),
        Output("kpis", "children"),
        Output("timeseries", "figure"),
        Output("diversion", "figure"),
        Output("freshness", "children"),
        Input("chokepoint", "value"),
        Input("vessel-type", "value"),
        Input("period", "value"),
        Input("data-version", "data"),  # changes after "Update data" -> redraw
    )
    def _update(chokepoint_id: str, vessel_type: str, period: str, _version: int) -> tuple:
        return update_views(state.data, chokepoint_id, vessel_type, period)

    @app.callback(
        Output("chokepoint", "value"),
        Input("map", "clickData"),
        prevent_initial_call=True,
    )
    def _select_on_map(click_data: dict | None) -> str:
        if not click_data:
            return no_update
        return click_data["points"][0]["customdata"]

    @app.callback(
        Output("refresh-status", "children"),
        Output("data-version", "data"),
        Input("refresh", "n_clicks"),
        State("data-version", "data"),
        prevent_initial_call=True,
    )
    def _refresh(_clicks: int, version: int) -> tuple[str, int]:
        new_days = state.refresh()
        return f"Updated: {new_days} new day(s)", version + 1
