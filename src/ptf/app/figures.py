"""Plotly figures of the shipping monitor. Pure functions: DataFrames in, figures out.

Colours follow one palette: blue = observed traffic, gray = normal (baseline), and a
diverging red <-> gray <-> blue scale for "below normal" vs. "above normal" on the map.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Palette (light theme)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BLUE = "#2a78d6"  # series 1: observed traffic / Red Sea route
ORANGE = "#eb6834"  # series 2: Cape route
RED = "#e34948"  # diverging pole: below normal
NEUTRAL = "#f0efec"  # diverging midpoint: normal
BASELINE_BAND = "rgba(137, 135, 129, 0.18)"
CRITICAL = "#d03b3b"
GOOD = "#006300"

VESSEL_LABELS = {
    "total": "all vessels",
    "container": "container ships",
    "tanker": "tankers",
    "dry_bulk": "dry bulk carriers",
    "general_cargo": "general cargo ships",
    "roro": "RoRo ships",
}

PERIODS = {"90d": 90, "1y": 365, "3y": 3 * 365, "all": None}
PERIOD_LABELS = {
    "90d": "Last 90 days",
    "1y": "Last 12 months",
    "3y": "Last 3 years",
    "all": "Since 2019",
}


def filter_period(frame: pd.DataFrame, period: str, latest: pd.Timestamp) -> pd.DataFrame:
    days = PERIODS[period]
    if days is None:
        return frame
    return frame[frame["date"] > latest - pd.Timedelta(days=days)]


def _base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"color": INK_SECONDARY, "size": 12},
        hovermode="x unified",
        # Legend below the plot, so it never collides with titles.
        legend={"orientation": "h", "y": -0.12, "x": 0, "yanchor": "top"},
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont={"color": MUTED})
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont={"color": MUTED})
    return fig


def map_figure(
    status: pd.DataFrame, chokepoints: pd.DataFrame, selected_id: str, vessel_type: str
) -> go.Figure:
    """All chokepoints: size = current 7-day traffic, colour = deviation from normal."""
    points = status.merge(chokepoints[["chokepoint_id", "lat", "lon"]], on="chokepoint_id")
    rolling = points["rolling"].fillna(0)
    size = 8 + 32 * np.sqrt(rolling / max(rolling.max(), 1))
    deviation = points["deviation_pct"].clip(-100, 100)
    label = VESSEL_LABELS[vessel_type]
    hover = [
        f"<b>{row.chokepoint}</b><br>{row.rolling:,.1f} {label} per day (7-day avg)"
        f"<br>{row.deviation_pct:+.0f} % vs. normal"
        + ("<br><b>Disrupted</b>" if row.is_disrupted else "")
        for row in points.itertuples()
    ]
    is_selected = points["chokepoint_id"] == selected_id

    fig = go.Figure(
        go.Scattergeo(
            lon=points["lon"],
            lat=points["lat"],
            customdata=points["chokepoint_id"],
            text=hover,
            hoverinfo="text",
            mode="markers",
            marker={
                "size": size,
                "color": deviation,
                "cmin": -100,
                "cmax": 100,
                "colorscale": [[0, RED], [0.5, NEUTRAL], [1, BLUE]],
                "colorbar": {"title": {"text": "% vs.<br>normal"}, "thickness": 10, "len": 0.7},
                # A dark ring marks the selected chokepoint; a light ring separates overlaps.
                "line": {
                    "color": np.where(is_selected, INK, SURFACE),
                    "width": np.where(is_selected, 3, 2),
                },
                "opacity": 0.95,
            },
        )
    )
    fig.update_geos(
        projection_type="natural earth",
        showcountries=False,
        showcoastlines=False,
        showland=True,
        landcolor="#ecebe6",
        showocean=True,
        oceancolor=SURFACE,
        showframe=False,
    )
    fig.update_layout(height=380, margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor=SURFACE)
    return fig


def timeseries_figure(table: pd.DataFrame, chokepoint: str, vessel_type: str) -> go.Figure:
    """Daily transits, 7-day average and normal band (min-max of 2019-2023) of one chokepoint."""
    label = VESSEL_LABELS[vessel_type]
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
            fillcolor=BASELINE_BAND,
            line={"width": 0},
            name="Normal range 2019-2023",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["baseline"],
            line={"color": INK_SECONDARY, "width": 1.5, "dash": "dot"},
            name="Normal (avg 2019-2023)",
            hovertemplate="%{y:.1f}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["value"],
            line={"color": MUTED, "width": 1},
            opacity=0.45,
            name="Daily",
            hovertemplate="%{y:.0f}",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=table["date"],
            y=table["rolling"],
            line={"color": BLUE, "width": 2},
            name="7-day average",
            hovertemplate="%{y:.1f}",
        )
    )
    fig.update_yaxes(
        title={"text": f"{label} per day", "font": {"color": MUTED}}, rangemode="tozero"
    )
    fig.update_layout(
        title={"text": f"{chokepoint}: {label} per day", "font": {"color": INK, "size": 14}}
    )
    return _base_layout(fig, height=400)


def diversion_figure(ratio: pd.DataFrame) -> go.Figure:
    """Red Sea vs. Cape route for container ships, and the Cape share below (no dual axis)."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.62, 0.38],
        vertical_spacing=0.08,
        subplot_titles=("Container ships per day (7-day average)", "Share taking the Cape route"),
    )
    fig.add_trace(
        go.Scatter(
            x=ratio["date"],
            y=ratio["red_sea_rolling"],
            line={"color": BLUE, "width": 2},
            name="Bab el-Mandeb (Red Sea)",
            hovertemplate="%{y:.1f}",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=ratio["date"],
            y=ratio["cape_rolling"],
            line={"color": ORANGE, "width": 2},
            name="Cape of Good Hope",
            hovertemplate="%{y:.1f}",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=ratio["date"],
            y=ratio["cape_share"] * 100,
            line={"color": INK_SECONDARY, "width": 2},
            name="Cape share",
            showlegend=False,
            hovertemplate="%{y:.0f} %",
        ),
        row=2,
        col=1,
    )
    fig.update_yaxes(rangemode="tozero", row=1, col=1)
    fig.update_yaxes(range=[0, 100], ticksuffix=" %", row=2, col=1)
    fig.update_annotations(font={"color": INK, "size": 13})
    return _base_layout(fig, height=460)


def kpis(status_row: pd.Series, vessel_type: str) -> list[dict]:
    """Values for the stat tiles of one chokepoint: label, value and an optional tone."""
    label = VESSEL_LABELS[vessel_type]
    deviation = status_row["deviation_pct"]
    yoy = status_row["yoy_pct"]
    disrupted = bool(status_row["is_disrupted"])
    return [
        {
            "label": f"{label.capitalize()} per day, last 7 days",
            "value": f"{status_row['rolling']:,.1f}",
        },
        {"label": "vs. normal (same week 2019-2023)", "value": _signed_pct(deviation)},
        {"label": "vs. same week last year", "value": _signed_pct(yoy)},
        {
            "label": "Status",
            "value": "▼ Disrupted" if disrupted else "● Normal range",
            "tone": CRITICAL if disrupted else GOOD,
        },
    ]


def _number(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value:,.1f}"


def _signed_pct(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value:+.0f} %"
