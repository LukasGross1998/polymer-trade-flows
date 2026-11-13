"""Reusable Plotly figures and Dash building blocks. Pure functions, no data loading."""

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html
from dash.development.base_component import Component

from ptf.app import style
from ptf.market_config import KeyEvent

# Return type of tab update functions: one value per Dash Output of the callback.
Outputs = tuple[Any, ...]

PERIODS = {"90d": 90, "1y": 365, "3y": 3 * 365, "5y": 5 * 365, "all": None}
PERIOD_LABELS = {
    "90d": "Last 90 days",
    "1y": "Last 12 months",
    "3y": "Last 3 years",
    "5y": "Last 5 years",
    "all": "All available",
}


def period_start(period: str, latest: pd.Timestamp, earliest: pd.Timestamp) -> pd.Timestamp:
    days = PERIODS[period]
    return earliest if days is None else latest - pd.Timedelta(days=days)


def filter_period(frame: pd.DataFrame, period: str, latest: pd.Timestamp) -> pd.DataFrame:
    days = PERIODS[period]
    if days is None:
        return frame
    return frame[frame["date"] > latest - pd.Timedelta(days=days)]


def base_layout(fig: go.Figure, height: int, title: str | None = None) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 55, "r": 20, "t": 50 if title else 20, "b": 40},
        paper_bgcolor=style.SURFACE,
        plot_bgcolor=style.SURFACE,
        font={"color": style.INK_SECONDARY, "size": 12},
        hovermode="x unified",
        # Legend below the plot, so it never collides with titles.
        legend={"orientation": "h", "y": -0.12, "x": 0, "yanchor": "top"},
    )
    if title:
        fig.update_layout(title={"text": title, "font": {"color": style.INK, "size": 14}})
    fig.update_xaxes(showgrid=False, linecolor=style.GRID, tickfont={"color": style.MUTED})
    fig.update_yaxes(gridcolor=style.GRID, zeroline=False, tickfont={"color": style.MUTED})
    return fig


def add_key_events(
    fig: go.Figure, key_events: list[KeyEvent], start: pd.Timestamp, end: pd.Timestamp
) -> go.Figure:
    """Dotted vertical lines with a short label for key events inside the visible period.

    The x-axis is fixed to [start, end]: otherwise Plotly widens the axis to make room for
    the label text. Labels alternate between two heights so neighbours do not overlap.
    """
    fig.update_xaxes(range=[start, end])
    visible = [e for e in key_events if start <= pd.Timestamp(e.date) <= end]
    for position, event in enumerate(visible):
        when = pd.Timestamp(event.date)
        # Events near the right edge get their label on the left of the line.
        near_right_edge = (when - start) / (end - start) > 0.75
        fig.add_vline(x=when, line={"color": style.MUTED, "width": 1, "dash": "dot"})
        fig.add_annotation(
            x=when,
            y=1 if position % 2 == 0 else 0.93,
            yref="paper",
            text=event.label,
            showarrow=False,
            xanchor="right" if near_right_edge else "left",
            yanchor="top",
            font={"size": 10, "color": style.INK_SECONDARY},
            bgcolor=style.SURFACE,
        )
    return fig


def location_map(
    status: pd.DataFrame,
    coordinates: pd.DataFrame,
    selected_id: str,
    value_label: str,
    events: pd.DataFrame | None = None,
    value_format: str = ",.1f",
) -> go.Figure:
    """Map of locations: size = current 7-day value, colour = deviation from normal.

    `status` comes from `latest_status`, `coordinates` has location_id, lat, lon.
    Active disruption events are drawn as gray crosses.
    """
    points = status.merge(coordinates[["location_id", "lat", "lon"]], on="location_id")
    rolling = points["rolling"].fillna(0)
    size = 8 + 32 * np.sqrt(rolling / max(rolling.max(), 1))
    hover = [
        f"<b>{row.location}</b><br>{row.rolling:{value_format}} {value_label} (7-day avg)"
        f"<br>{row.deviation_pct:+.0f} % vs. normal"
        + ("<br><b>▼ Disrupted</b>" if row.is_disrupted else "")
        for row in points.itertuples()
    ]
    is_selected = points["location_id"] == selected_id

    fig = go.Figure(
        go.Scattergeo(
            lon=points["lon"],
            lat=points["lat"],
            customdata=points["location_id"],
            text=hover,
            hoverinfo="text",
            mode="markers",
            name="",
            showlegend=False,
            marker={
                "size": size,
                "color": points["deviation_pct"].clip(-100, 100),
                "cmin": -100,
                "cmax": 100,
                "colorscale": [[0, style.RED], [0.5, style.NEUTRAL], [1, style.BLUE]],
                "colorbar": {"title": {"text": "% vs.<br>normal"}, "thickness": 10, "len": 0.7},
                # A dark ring marks the selected location; a light ring separates overlaps.
                "line": {
                    "color": np.where(is_selected, style.INK, style.SURFACE),
                    "width": np.where(is_selected, 3, 2),
                },
                "opacity": 0.95,
            },
        )
    )
    if events is not None and not events.empty:
        fig.add_trace(
            go.Scattergeo(
                lon=events["lon"],
                lat=events["lat"],
                text=[
                    f"<b>{e.event}</b><br>since {e.from_date:%d %b %Y}" for e in events.itertuples()
                ],
                hoverinfo="text",
                mode="markers",
                name="Active disruption event",
                marker={"symbol": "x", "size": 11, "color": style.INK_SECONDARY},
                showlegend=True,
            )
        )
    fig.update_geos(
        projection_type="natural earth",
        showcountries=False,
        showcoastlines=False,
        showland=True,
        landcolor=style.LAND,
        showocean=True,
        oceancolor=style.SURFACE,
        showframe=False,
    )
    fig.update_layout(
        height=380,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor=style.SURFACE,
        legend={"orientation": "h", "y": 0.02, "x": 0.01},
    )
    return fig


def location_timeseries(table: pd.DataFrame, title: str, y_label: str) -> go.Figure:
    """Daily values, 7-day average and the normal band (min-max of the baseline years)."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["baseline_high"],
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["baseline_low"],
            fill="tonexty",
            fillcolor=style.BASELINE_BAND,
            line={"width": 0},
            name="Normal range 2019-2023",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["baseline"],
            line={"color": style.INK_SECONDARY, "width": 1.5, "dash": "dot"},
            name="Normal (avg 2019-2023)",
            hovertemplate="%{y:,.1f}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["value"],
            line={"color": style.MUTED, "width": 1},
            opacity=0.45,
            name="Daily",
            hovertemplate="%{y:,.0f}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["rolling"],
            line={"color": style.BLUE, "width": 2},
            name="7-day average",
            hovertemplate="%{y:,.1f}",
        )
    )
    fig.update_yaxes(title={"text": y_label, "font": {"color": style.MUTED}}, rangemode="tozero")
    return base_layout(fig, height=400, title=title)


def line_chart(frames: list[tuple[str, pd.DataFrame]], title: str, y_label: str) -> go.Figure:
    """One line per (name, DataFrame with date and value), colours in fixed order.

    The colour belongs to the position in `frames`, so a missing (empty) series is skipped
    without repainting the others.
    """
    fig = go.Figure()
    for colour, (name, frame) in zip(style.SERIES, frames, strict=False):
        if frame.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=frame["date"],
                y=frame["value"],
                name=name,
                line={"color": colour, "width": 2},
                hovertemplate="%{y:,.2f}",
            )
        )
    fig.update_yaxes(title={"text": y_label, "font": {"color": style.MUTED}})
    return base_layout(fig, height=340, title=title)


# --- Dash building blocks --------------------------------------------------------------------


def control(label: str, component: Component) -> html.Div:
    return html.Div(
        [html.Label(label, style={"fontSize": "12px", "color": style.MUTED}), component],
        style=style.CONTROL,
    )


def period_dropdown(component_id: str, value: str = "3y") -> dcc.Dropdown:
    return dcc.Dropdown(
        id=component_id,
        options=[{"label": v, "value": k} for k, v in PERIOD_LABELS.items()],
        value=value,
        clearable=False,
    )


def graph(component_id: str) -> dcc.Graph:
    return dcc.Graph(id=component_id, config={"displayModeBar": False, "scrollZoom": False})


def tiles(values: list[dict[str, str]]) -> list[html.Div]:
    """Stat tiles: dicts with label, value and optional tone (only for status values)."""
    out = []
    for item in values:
        value_style = {
            "fontSize": "24px",
            "fontWeight": "600",
            "color": item.get("tone", style.INK),
        }
        children = [
            html.Div(item["label"], style={"fontSize": "12px", "color": style.MUTED}),
            html.Div(item["value"], style=value_style),
        ]
        if item.get("note"):
            children.append(
                html.Div(item["note"], style={"fontSize": "11px", "color": style.MUTED})
            )
        out.append(html.Div(children, style={**style.CARD, "flex": "1", "minWidth": "200px"}))
    return out


def status_value(disrupted: bool) -> dict[str, str]:
    """Status text with icon and colour: never colour alone."""
    if disrupted:
        return {"value": "▼ Disrupted", "tone": style.CRITICAL}
    return {"value": "● Normal range", "tone": style.GOOD}


def number(value: float | None, fmt: str = ",.1f") -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:{fmt}}"


def signed_pct(value: float | None) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:+.0f} %"


def no_data(message: str) -> html.Div:
    return html.Div(message, style={**style.CARD, "color": style.MUTED})
