"""Tab "Trade flows": the port-to-port shipping network and countries' trade by cargo type."""

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, no_update

from ptf.app import charts, style
from ptf.app.data import AppData, AppState, require
from ptf.monitor.flows import cargo_mix, country_ranking, port_options, top_links
from ptf.monitor.vocabulary import CARGO_TYPES

ALL_PORTS = "__all__"
DEFAULT_COUNTRY = "SAU"  # Saudi Arabia: the Hormuz disruption is visible in its tanker exports
CARGO_SHORT = {
    "tanker": "Tankers",
    "dry_bulk": "Dry bulk",
    "container": "Containers",
    "general_cargo": "General cargo",
    "roro": "RoRo",
}


COUNTRY_TRADE_HINT = (
    "Trade by cargo type: no data yet. The country trade dataset (~560,000 rows) takes 20-25 "
    "minutes to download the first time. To enable it, set `download_country_trade: true` in "
    "config/monitor.yaml and run `uv run python -m ptf.pipeline portwatch`."
)


def layout(data: AppData) -> html.Div:
    if data.port_links is None:
        return charts.no_data("No flow data yet: run `uv run python -m ptf.pipeline portwatch`.")
    trade = charts.no_data(COUNTRY_TRADE_HINT)
    if data.country_trade is not None:
        trade = _trade_section(data)
    return html.Div([_network_section(data), trade])


def _network_section(data: AppData) -> html.Div:
    ports = port_options(require(data.port_links, "port_links"))
    port_choices = [{"label": "All ports (largest links worldwide)", "value": ALL_PORTS}] + [
        {"label": f"{p.port} ({p.country})", "value": p.port_id} for p in ports.itertuples()
    ]
    return html.Div(
        [
            html.Div("Port-to-port shipping network", style=style.SECTION_TITLE),
            html.Div(
                [
                    charts.control(
                        "Port (or click a port on the map)",
                        dcc.Dropdown(
                            id="flow-port", options=port_choices, value=ALL_PORTS, clearable=False
                        ),
                    ),
                    charts.control(
                        "Direction",
                        dcc.RadioItems(
                            id="flow-direction",
                            options=[
                                {"label": " Outbound", "value": "outbound"},
                                {"label": " Inbound", "value": "inbound"},
                            ],
                            value="outbound",
                            inline=True,
                            inputStyle={"marginLeft": "12px"},
                        ),
                    ),
                    charts.control(
                        "Links",
                        dcc.Checklist(
                            id="flow-long-haul",
                            options=[
                                {
                                    "label": " Long-haul links only (international, 5+ days)",
                                    "value": "long",
                                }
                            ],
                            value=["long"],
                        ),
                    ),
                ],
                style=style.ROW,
            ),
            html.Div(
                [
                    html.Div(charts.graph("flow-map"), style={"flex": "2", "minWidth": "480px"}),
                    html.Div(id="flow-table", style={"flex": "1", "minWidth": "280px"}),
                ],
                style=style.ROW,
            ),
            html.Div(
                "Source: IMF PortWatch port-to-port network (snapshot, last updated May 2025), all "
                "vessel types together. Line width = vessel capacity (deadweight tonnes) "
                "travelling between the ports per day, not the cargo actually carried. Only links "
                "with at "
                "least 1,000 t of daily capacity are included.",
                style=style.SMALL_NOTE,
            ),
        ],
        style={**style.CARD, "marginBottom": "16px"},
    )


def _trade_section(data: AppData) -> html.Div:
    trade = require(data.country_trade, "country_trade")
    countries = trade[["iso3", "country"]].drop_duplicates().sort_values("country")
    country_choices = [{"label": c.country, "value": c.iso3} for c in countries.itertuples()]
    return html.Div(
        [
            html.Div("Trade by cargo type", style=style.SECTION_TITLE),
            html.Div(
                [
                    charts.control(
                        "Country",
                        dcc.Dropdown(
                            id="flow-country",
                            options=country_choices,
                            value=DEFAULT_COUNTRY,
                            clearable=False,
                        ),
                    ),
                    charts.control(
                        "Flow",
                        dcc.RadioItems(
                            id="flow-flow",
                            options=[
                                {"label": " Exports", "value": "export"},
                                {"label": " Imports", "value": "import"},
                            ],
                            value="export",
                            inline=True,
                            inputStyle={"marginLeft": "12px"},
                        ),
                    ),
                    charts.control(
                        "Cargo type for the ranking",
                        dcc.Dropdown(
                            id="flow-cargo",
                            options=[{"label": v, "value": k} for k, v in CARGO_SHORT.items()],
                            value="tanker",
                            clearable=False,
                        ),
                    ),
                    charts.control("Period", charts.period_dropdown("flow-period")),
                ],
                style=style.ROW,
            ),
            html.Div(
                [
                    html.Div(charts.graph("flow-mix"), style={"flex": "1", "minWidth": "420px"}),
                    html.Div(
                        charts.graph("flow-ranking"), style={"flex": "1", "minWidth": "420px"}
                    ),
                ],
                style=style.ROW,
            ),
            html.Div(
                "Source: IMF PortWatch daily trade estimates per country from vessel draught and "
                "capacity (t/day), not customs statistics. Vessel type stands for the cargo: "
                + "; ".join(f"{CARGO_SHORT[k]} = {v}" for k, v in CARGO_TYPES.items())
                + ".",
                style=style.SMALL_NOTE,
            ),
        ],
        style=style.CARD,
    )


def _width_bucket(capacity: pd.Series) -> pd.Series:
    """Four line widths by capacity quartile: thin marks stay readable on a world map."""
    ranks = capacity.rank(pct=True)
    return pd.cut(ranks, [0, 0.25, 0.5, 0.75, 1.0], labels=[1.0, 2.0, 3.5, 5.0]).astype(float)


def network_figure(links: pd.DataFrame, selected_port: str | None) -> go.Figure:
    """Flow lines between ports (one trace per width bucket), port markers and link hovers."""
    fig = go.Figure()
    if links.empty:
        return charts.base_layout(fig, height=420)

    links = links.assign(width=_width_bucket(links["daily_capacity"]))
    for width, group in links.groupby("width"):
        lon: list[float | None] = []
        lat: list[float | None] = []
        for row in group.to_dict("records"):
            lon += [row["from_lon"], row["to_lon"], None]  # None breaks the line between links
            lat += [row["from_lat"], row["to_lat"], None]
        fig.add_trace(
            go.Scattergeo(
                lon=lon,
                lat=lat,
                mode="lines",
                line={"width": width, "color": style.BLUE},
                opacity=0.45,
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Invisible markers in the middle of each link carry the hover text.
    fig.add_trace(
        go.Scattergeo(
            lon=(links["from_lon"] + links["to_lon"]) / 2,
            lat=(links["from_lat"] + links["to_lat"]) / 2,
            mode="markers",
            marker={"size": 8, "opacity": 0},
            text=[
                f"<b>{r.from_port} → {r.to_port}</b><br>{r.daily_capacity:,.0f} t capacity per day"
                f"<br>{r.transit_days:.1f} days transit"
                for r in links.itertuples()
            ],
            hoverinfo="text",
            showlegend=False,
        )
    )

    ports = (
        pd.concat(
            [
                links[
                    ["from_port_id", "from_port", "from_lat", "from_lon", "daily_capacity"]
                ].set_axis(["port_id", "port", "lat", "lon", "capacity"], axis=1),
                links[["to_port_id", "to_port", "to_lat", "to_lon", "daily_capacity"]].set_axis(
                    ["port_id", "port", "lat", "lon", "capacity"], axis=1
                ),
            ]
        )
        .groupby(["port_id", "port", "lat", "lon"], as_index=False)["capacity"]
        .sum()
    )
    is_selected = ports["port_id"] == selected_port
    fig.add_trace(
        go.Scattergeo(
            lon=ports["lon"],
            lat=ports["lat"],
            customdata=ports["port_id"],
            text=[
                f"<b>{p.port}</b><br>{p.capacity:,.0f} t capacity per day on shown links"
                for p in ports.itertuples()
            ],
            hoverinfo="text",
            mode="markers",
            marker={
                "size": 5 + 14 * np.sqrt(ports["capacity"] / ports["capacity"].max()),
                "color": np.where(is_selected, style.ORANGE, style.INK_SECONDARY),
                "line": {"color": style.SURFACE, "width": 1},
            },
            showlegend=False,
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
        height=420, margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor=style.SURFACE
    )
    return fig


def links_table(links: pd.DataFrame, n: int = 12) -> html.Div:
    """The largest links of the current selection as a compact table."""
    if links.empty:
        return html.Div("No links above the capacity threshold.", style={"color": style.MUTED})
    header = html.Tr(
        [
            html.Th(t, style={"textAlign": "left", "fontSize": "12px", "color": style.MUTED})
            for t in ["From → to", "t/day", "days"]
        ]
    )
    rows = [
        html.Tr(
            [
                html.Td(f"{r.from_port} → {r.to_port}"),
                html.Td(f"{r.daily_capacity:,.0f}"),
                html.Td(f"{r.transit_days:.1f}"),
            ],
            style={"fontSize": "13px"},
        )
        for r in links.head(n).itertuples()
    ]
    return html.Div(
        [
            html.Div("Largest links", style={**style.SECTION_TITLE, "fontSize": "13px"}),
            html.Table([header, *rows], style={"width": "100%", "borderCollapse": "collapse"}),
        ]
    )


def mix_figure(mix: pd.DataFrame, title: str) -> go.Figure:
    """Stacked areas by cargo type; colours tied to the cargo type, in fixed order."""
    fig = go.Figure()
    for colour, cargo_type in zip(style.SERIES, CARGO_TYPES, strict=True):
        one = mix[mix["cargo_type"] == cargo_type]
        fig.add_trace(
            go.Scatter(
                x=one["date"],
                y=one["value"],
                name=CARGO_SHORT[cargo_type],
                stackgroup="cargo",
                line={"width": 0.5, "color": colour},
                fillcolor=colour,
                hovertemplate="%{y:,.0f} t",
            )
        )
    fig.update_yaxes(title={"text": "t per day (30-day average)", "font": {"color": style.MUTED}})
    return charts.base_layout(fig, height=400, title=title)


def ranking_figure(ranking: pd.DataFrame, title: str) -> go.Figure:
    """Horizontal bars: 7-day average, with the deviation from normal as text label."""
    ordered = ranking.iloc[::-1]  # largest on top
    labels = [
        ("▼ " if r["is_disrupted"] else "") + charts.signed_pct(r["deviation_pct"]) + " vs. normal"
        for r in ordered.to_dict("records")
    ]
    fig = go.Figure(
        go.Bar(
            x=ordered["rolling"],
            y=ordered["location"],
            orientation="h",
            marker={"color": style.BLUE},
            text=labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x:,.0f} t per day<extra></extra>",
        )
    )
    fig.update_xaxes(title={"text": "t per day, last 7 days", "font": {"color": style.MUTED}})
    charts.base_layout(fig, height=400, title=title)
    fig.update_layout(hovermode="closest", margin={"l": 140, "r": 110})
    return fig


def update_network(
    data: AppData, port_id: str, direction: str, long_haul: list[str]
) -> charts.Outputs:
    port = None if port_id == ALL_PORTS else port_id
    links = top_links(
        require(data.port_links, "port_links"),
        n=150 if port is None else 40,
        port_id=port,
        direction=direction,
        long_haul_only="long" in long_haul,
    )
    return network_figure(links, port), links_table(links)


def update_trade(
    data: AppData, iso3: str, flow: str, cargo_type: str, period: str
) -> charts.Outputs:
    trade = require(data.country_trade, "country_trade")
    latest = trade["date"].max()
    name = trade[trade["iso3"] == iso3]["country"].iloc[0]
    mix = charts.filter_period(cargo_mix(trade, iso3, flow), period, latest)
    start = charts.period_start(period, latest, trade["date"].min())
    mix_fig = mix_figure(mix, f"{name}: {flow}s by cargo type")
    charts.add_key_events(mix_fig, data.market_config.key_events, start, latest)
    ranking = country_ranking(trade, flow, cargo_type, data.monitor_config)
    ranking_fig = ranking_figure(ranking, f"Largest {flow}ers: {CARGO_SHORT[cargo_type].lower()}")
    return mix_fig, ranking_fig


def register(app: Dash, state: AppState) -> None:
    if state.data.port_links is None:
        return

    @app.callback(
        Output("flow-map", "figure"),
        Output("flow-table", "children"),
        Input("flow-port", "value"),
        Input("flow-direction", "value"),
        Input("flow-long-haul", "value"),
        Input("data-version", "data"),
    )
    def _network(
        port_id: str, direction: str, long_haul: list[str], _version: int
    ) -> charts.Outputs:
        return update_network(state.data, port_id, direction, long_haul)

    if state.data.country_trade is not None:
        _register_trade(app, state)

    @app.callback(
        Output("flow-port", "value"), Input("flow-map", "clickData"), prevent_initial_call=True
    )
    def _select_port(click_data: dict[str, Any] | None) -> object:
        point = (click_data or {}).get("points", [{}])[0]
        return point.get("customdata") or no_update  # only port markers carry an id


def _register_trade(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("flow-mix", "figure"),
        Output("flow-ranking", "figure"),
        Input("flow-country", "value"),
        Input("flow-flow", "value"),
        Input("flow-cargo", "value"),
        Input("flow-period", "value"),
        Input("data-version", "data"),
    )
    def _trade(iso3: str, flow: str, cargo_type: str, period: str, _version: int) -> charts.Outputs:
        return update_trade(state.data, iso3, flow, cargo_type, period)
