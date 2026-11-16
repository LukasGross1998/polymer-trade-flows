"""Weather card for the chokepoint and port tabs (spec 009): waves and gusts, past and forecast.

Two small charts instead of one with two axes; observed days solid, forecast dashed; the
storm thresholds of `config/shipping.yaml` as dotted lines.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import html

from ptf.app import charts, theme
from ptf.app.data import AppData
from ptf.shipping.config import Threshold, WeatherConfig
from ptf.shipping.weather import RED, storm_warnings

LEVEL_STYLE = {RED: ("▲ Storm", theme.CRITICAL), "amber": ("▲ Gale", theme.WARNING)}


def layout(prefix: str, config: WeatherConfig) -> html.Div:
    """Card with two graphs and a note; ids `{prefix}-waves`, `{prefix}-gusts`, `{prefix}-note`."""
    graph = {"flex": "1", "minWidth": "300px"}
    return html.Div(
        [
            html.Div("Marine weather: past 7 days and 7-day forecast", style=theme.SECTION_TITLE),
            html.Div(id=f"{prefix}-note", style={"fontSize": "13px", "marginBottom": "4px"}),
            html.Div(
                [
                    html.Div(charts.graph(f"{prefix}-waves"), style=graph),
                    html.Div(charts.graph(f"{prefix}-gusts"), style=graph),
                ],
                style={"display": "flex", "gap": "16px", "flexWrap": "wrap"},
            ),
            theme.method_panel(
                "Source: Open-Meteo (marine and weather models, daily maxima). Gale from "
                f"{config.gusts_kmh.amber:g} km/h gusts (Beaufort 8 'gale', Met Office) "
                f"or {config.waves_m.amber:g} m waves (WMO sea state 'very rough'); storm from "
                f"{config.gusts_kmh.red:g} km/h (Beaufort 10 'storm') or "
                f"{config.waves_m.red:g} m ('high'). Points on land have no wave data.",
            ),
        ],
        style={**theme.CARD, "marginTop": "16px"},
    )


def _figure(
    rows: pd.DataFrame, column: str, title: str, unit: str, threshold: Threshold
) -> go.Figure:
    fig = go.Figure()
    for is_forecast, name, dash in [(False, "observed", "solid"), (True, "forecast", "dash")]:
        part = rows[rows["is_forecast"] == is_forecast]
        if is_forecast and not rows[~rows["is_forecast"]].empty:
            part = pd.concat([rows[~rows["is_forecast"]].tail(1), part])  # connect the lines
        fig.add_trace(
            go.Scatter(
                x=part["date"],
                y=part[column],
                name=name,
                mode="lines+markers",
                line={"color": theme.BLUE, "width": 2, "dash": dash},
                hovertemplate="%{x|%d %b}: %{y:.1f} " + unit + "<extra>" + name + "</extra>",
            )
        )
    for value, colour in [(threshold.amber, theme.WARNING), (threshold.red, theme.CRITICAL)]:
        fig.add_hline(y=value, line={"color": colour, "width": 1, "dash": "dot"})
    fig.update_yaxes(title={"text": unit, "font": {"color": theme.MUTED}}, rangemode="tozero")
    charts.base_layout(fig, height=230, title=title)
    fig.update_layout(showlegend=False, margin={"l": 45, "r": 10, "t": 40, "b": 30})
    return fig


def update(
    data: AppData, location_id: str, today: pd.Timestamp | None = None
) -> tuple[go.Figure, go.Figure, html.Span]:
    """Figures and the warning note for one chokepoint or port."""
    empty = go.Figure()
    if data.weather is None:
        return empty, empty, html.Span("No weather data loaded yet.")
    rows = data.weather[data.weather["location_id"] == location_id].sort_values("date")
    if rows.empty:
        return empty, empty, html.Span("No weather data for this location.")
    config = data.monitor_config.weather
    waves = _figure(rows, "wave_height_m", "Wave height, daily maximum", "m", config.waves_m)
    gusts = _figure(rows, "wind_gusts_kmh", "Wind gusts, daily maximum", "km/h", config.gusts_kmh)
    today = today if today is not None else pd.Timestamp(pd.Timestamp.now(tz="UTC").date())
    warnings = storm_warnings(rows, today, config)
    if warnings.empty:
        note = html.Span("● No gale or storm in the forecast", style={"color": theme.GOOD})
    else:
        first = warnings.iloc[0]
        label, colour = LEVEL_STYLE.get(first["level"], ("", theme.INK))
        waves_m = charts.number(first["wave_height_m"])
        gusts_kmh = charts.number(first["wind_gusts_kmh"], ",.0f")
        note = html.Span(
            f"{label} forecast on {first['date']:%d %b}: waves {waves_m} m, gusts {gusts_kmh} km/h",
            style={"color": colour, "fontWeight": "600"},
        )
    return waves, gusts, note
