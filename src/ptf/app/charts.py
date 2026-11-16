"""Reusable Plotly figures and Dash building blocks. Pure functions, no data loading."""

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html
from dash.development.base_component import Component

from ptf.app import fmt, theme
from ptf.markets.config import KeyEvent

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
    """Size and hover of a figure; colours and fonts come from the theme's Plotly template.

    The title is kept in the figure only as data: the card shows it above the plot
    (`graph()`, spec 017), and the stylesheet hides Plotly's own title.
    """
    fig.update_layout(
        template="ptf",
        height=height,
        margin={"l": 55, "r": 20, "t": 16, "b": 40},
        hovermode="x unified",
    )
    if title:
        fig.update_layout(title={"text": title})
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
        fig.add_vline(x=when, line={"color": theme.MUTED, "width": 1, "dash": "dot"})
        fig.add_annotation(
            x=when,
            y=1 if position % 2 == 0 else 0.93,
            yref="paper",
            text=event.label,
            showarrow=False,
            xanchor="right" if near_right_edge else "left",
            yanchor="top",
            font={"size": 10, "color": theme.INK_SECONDARY},
            bgcolor=theme.SURFACE,
        )
    return fig


# OpenSeaMap seamarks (buoys, lights, harbours) as a transparent raster layer (spec 009).
SEAMARK_TILES = "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png"


def location_map(
    status: pd.DataFrame,
    coordinates: pd.DataFrame,
    selected_id: str,
    value_label: str,
    events: pd.DataFrame | None = None,
    value_format: str = ",.1f",
    seamarks: bool = False,
) -> go.Figure:
    """Tile map of locations: size = current 7-day value, colour = deviation from normal.

    `status` comes from `latest_status`, `coordinates` has location_id, lat, lon.
    Active disruption events are drawn as small gray dots; with `seamarks` the OpenSeaMap
    layer is drawn on top of the base map. Base map and seamarks are loaded by the browser.
    """
    points = status.merge(coordinates[["location_id", "lat", "lon"]], on="location_id")
    rolling = points["rolling"].fillna(0)
    size = 8 + 32 * np.sqrt(rolling / max(rolling.max(), 1))
    hover = [
        f"<b>{row.location}</b><br>{row.rolling:{value_format}} {value_label} (7-day avg)"
        f"<br>{fmt.pct(deviation)} vs. normal"
        + ("<br><b>▼ Disrupted</b>" if row.is_disrupted else "")
        for row, deviation in zip(
            points.itertuples(), points["deviation_pct"].astype(float).tolist(), strict=True
        )
    ]
    is_selected = (points["location_id"] == selected_id).to_numpy()

    fig = go.Figure()
    # Tile-map markers have no outline, so a slightly larger dark dot behind the selected
    # location marks it.
    fig.add_trace(
        go.Scattermap(
            lon=points.loc[is_selected, "lon"],
            lat=points.loc[is_selected, "lat"],
            customdata=points.loc[is_selected, "location_id"],
            mode="markers",
            hoverinfo="skip",
            showlegend=False,
            marker={"size": size[is_selected] + 8, "color": theme.INK},
        )
    )
    fig.add_trace(
        go.Scattermap(
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
                "colorscale": [[0, theme.DIVERGING_LOW], [0.5, theme.NEUTRAL], [1, theme.BLUE]],
                "colorbar": {"title": {"text": "% vs.<br>normal"}, "thickness": 10, "len": 0.7},
                "opacity": 0.9,
            },
        )
    )
    if events is not None and not events.empty:
        fig.add_trace(
            go.Scattermap(
                lon=events["lon"],
                lat=events["lat"],
                text=[
                    f"<b>{e.event}</b><br>since {e.from_date:%d %b %Y}" for e in events.itertuples()
                ],
                hoverinfo="text",
                mode="markers",
                name="Active disruption event",
                marker={"size": 9, "color": theme.INK_SECONDARY},
                showlegend=True,
            )
        )
    # Seamarks only show from about zoom 8 on, so the chart layer also zooms to the selection.
    center, zoom = {"lat": 20.0, "lon": 45.0}, 0.7
    layers = []
    if seamarks:
        layers = [{"sourcetype": "raster", "source": [SEAMARK_TILES], "below": "traces"}]
        chosen = points[is_selected]
        if not chosen.empty:
            center = {"lat": float(chosen["lat"].iloc[0]), "lon": float(chosen["lon"].iloc[0])}
            zoom = 8.0
    fig.update_layout(
        map={
            "style": "carto-positron",
            "center": center,
            "zoom": zoom,
            "layers": layers,
        },
        height=380,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor=theme.SURFACE,
        legend={"orientation": "h", "y": 0.02, "x": 0.01},
    )
    return fig


def seamark_switch(component_id: str) -> dcc.Checklist:
    """Switch for the OpenSeaMap layer on the location maps."""
    return dcc.Checklist(
        id=component_id,
        options=[{"label": " Nautical chart layer (OpenSeaMap)", "value": "on"}],
        value=[],
        inputStyle={"marginRight": "4px"},
    )


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
            fillcolor=theme.BASELINE_BAND,
            line={"width": 0},
            name="Normal range 2019-2023",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["baseline"],
            line={"color": theme.INK_SECONDARY, "width": 1.5, "dash": "dot"},
            name="Normal (avg 2019-2023)",
            hovertemplate="%{y:,.1f}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["value"],
            line={"color": theme.MUTED, "width": 1},
            opacity=0.45,
            name="Daily",
            hovertemplate="%{y:,.0f}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["rolling"],
            line={"color": theme.BLUE, "width": 2},
            name="7-day average",
            hovertemplate="%{y:,.1f}",
        )
    )
    fig.update_yaxes(title={"text": y_label, "font": {"color": theme.MUTED}}, rangemode="tozero")
    return base_layout(fig, height=400, title=title)


def line_chart(frames: list[tuple[str, pd.DataFrame]], title: str, y_label: str) -> go.Figure:
    """One line per (name, DataFrame with date and value), colours in fixed order.

    The colour belongs to the position in `frames`, so a missing (empty) series is skipped
    without repainting the others.
    """
    fig = go.Figure()
    for colour, (name, frame) in zip(theme.SERIES, frames, strict=False):
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
    fig.update_yaxes(title={"text": y_label, "font": {"color": theme.MUTED}})
    return base_layout(fig, height=340, title=title)


# --- Dash building blocks --------------------------------------------------------------------


def control(label: str, component: Component) -> html.Div:
    return html.Div(
        [html.Label(label, style={"fontSize": "12px", "color": theme.MUTED}), component],
        style=theme.CONTROL,
    )


def period_dropdown(component_id: str, value: str = "3y") -> dcc.Dropdown:
    return dcc.Dropdown(
        id=component_id,
        options=[{"label": v, "value": k} for k, v in PERIOD_LABELS.items()],
        value=value,
        clearable=False,
    )


# Ids of all graphs built with `graph()`; the app copies each figure's title into its card.
GRAPH_IDS: list[str] = []


def graph(component_id: str) -> html.Div:
    """A chart with its title as a card title above the plot (spec 017)."""
    if component_id not in GRAPH_IDS:
        GRAPH_IDS.append(component_id)
    return html.Div(
        [
            html.Div(id=f"{component_id}-title", style=theme.CARD_TITLE),
            dcc.Graph(
                id=component_id,
                className="ptf-graph",
                config={"displayModeBar": False, "scrollZoom": False},
            ),
        ]
    )


TITLE_FROM_FIGURE = """
function(figure) {
    var title = figure && figure.layout && figure.layout.title;
    if (!title) { return ""; }
    return (typeof title === "string" ? title : title.text || "").replace(/<[^>]*>/g, " ");
}
"""


def register_graph_titles(app: Any) -> None:
    """One small browser-side callback per graph: figure title -> card title."""
    for component_id in GRAPH_IDS:
        app.clientside_callback(
            TITLE_FROM_FIGURE,
            Output(f"{component_id}-title", "children"),
            Input(component_id, "figure"),
        )


def tiles(values: list[dict[str, Any]]) -> list[html.Div]:
    """KPI tiles, one component for all tabs (spec 017). Keys per tile:

    label, value (required); unit; delta (e.g. "+3.0 % vs. 30 days"); date (data date or
    basis, e.g. "13 Nov 2026" or "BACI 2024"); tone (a status colour, only with an icon and
    word in the value); note; spark (DataFrame with date and value for a sparkline).
    """
    out = []
    for item in values:
        value_style = {
            "fontSize": "24px",
            "fontWeight": "600",
            "color": item.get("tone", theme.INK),
        }
        value: list[Component | str] | str = str(item["value"])
        if item.get("unit"):
            value = [str(item["value"])]
            value.append(
                html.Span(
                    f"{fmt.THIN}{item['unit']}",
                    style={"fontSize": "13px", "fontWeight": "400", "color": theme.MUTED},
                )
            )
        children: list[Component] = [
            html.Div(item["label"], style={"fontSize": "12px", "color": theme.MUTED}),
            html.Div(value, style=value_style),
        ]
        small = {"fontSize": "11px", "color": theme.MUTED}
        if item.get("delta"):
            children.append(html.Div(item["delta"], style={**small, "color": theme.INK_SECONDARY}))
        if item.get("note"):
            children.append(html.Div(item["note"], style=small))
        if item.get("date"):
            children.append(html.Div(f"Data: {item['date']}", style=small))
        spark = item.get("spark")
        if spark is not None and not spark.empty:
            children.append(sparkline(spark))
        out.append(html.Div(children, style={**theme.CARD, "flex": "1", "minWidth": "200px"}))
    return out


def sparkline(frame: pd.DataFrame, colour: str = theme.BLUE) -> dcc.Graph:
    """A small line without axes for a tile."""
    fig = go.Figure(
        go.Scatter(
            x=frame["date"],
            y=frame["value"],
            mode="lines",
            line={"color": colour, "width": 1.5},
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        template="ptf",
        height=40,
        margin={"l": 0, "r": 0, "t": 4, "b": 0},
        showlegend=False,
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "staticPlot": True})


def delta_text(change_pct: float | None, period: str) -> str:
    """'+3.0 % vs. 30 days' with a true minus sign; '' without a value."""
    return "" if change_pct is None else f"{fmt.pct(change_pct)} vs. {period}"


def status_value(disrupted: bool) -> dict[str, str]:
    """Status text with icon and colour: never colour alone."""
    if disrupted:
        return {"value": "▼ Disrupted", "tone": theme.CRITICAL}
    return {"value": "● Normal range", "tone": theme.GOOD}


def number(value: float | None, spec: str = ",.1f") -> str:
    return "n/a" if value is None or pd.isna(value) else fmt._minus(f"{value:{spec}}")


def signed_pct(value: float | None) -> str:
    return fmt.pct(None if value is None or pd.isna(value) else float(value))


def no_data(message: str) -> html.Div:
    return html.Div(message, style={**theme.CARD, "color": theme.MUTED})
