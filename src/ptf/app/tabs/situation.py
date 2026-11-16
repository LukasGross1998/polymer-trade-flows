"""Tab "Situation": do I need to act today? Start page for a polyethylene buyer in Europe.

Four cards (price, supply, logistics with graded traffic lights; polyethylene as an
indicator), each with a link to the tab that explains it; what changed in the last 7 days
and the chokepoints and events that matter for Europe (spec 013). Method notes sit in
info icons, not in the layout.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html
from dash.development.base_component import Component

from ptf.app import charts, fmt, theme
from ptf.app.data import AppData, AppState
from ptf.app.tabs import prices
from ptf.insights import relevance, signals
from ptf.insights.config import Threshold
from ptf.insights.scenario import LIVE
from ptf.insights.view import ALL_GRADES, traffic_lights
from ptf.markets import indicators
from ptf.shipping.metrics import latest_status
from ptf.shipping.overview import active_events, furthest_below_normal
from ptf.shipping.vocabulary import EVENT_TYPES
from ptf.shipping.weather import storm_warnings

# Icon + word + colour, never colour alone.
LEVELS = {
    signals.GREEN: ("●", "OK", theme.GOOD),
    signals.YELLOW: ("◆", "Watch", theme.WARNING),
    signals.ORANGE: ("▲", "Elevated", theme.ELEVATED),
    signals.RED: ("▲", "Critical", theme.CRITICAL),
}
# Card -> (link text, tab it opens).
ACTIONS = {
    "Price": ("Review drivers →", "prices"),
    "Supply": ("Check routes →", "sourcing"),
    "Logistics": ("View delays →", "planner"),
    "Polyethylene": ("See PE prices →", "prices"),
}
EUROPE, ALL = "europe", "all"


def info(text: str) -> html.Span:
    """An (i) icon whose tooltip carries the method note."""
    return html.Span(
        " ⓘ", title=text, style={"cursor": "help", "color": theme.MUTED, "fontWeight": "400"}
    )


def heading(text: str, note: str) -> html.Div:
    return html.Div([text, info(note)], style=theme.SECTION_TITLE)


def layout(data: AppData) -> html.Div:
    card = {**theme.CARD, "flex": "1", "minWidth": "300px"}
    days = data.sourcing_config.recent_days
    return html.Div(
        [
            html.Div(
                dcc.RadioItems(
                    id="sit-scope",
                    options=[
                        {"label": "Relevant for Europe", "value": EUROPE},
                        {"label": "All regions", "value": ALL},
                    ],
                    value=EUROPE,
                    inline=True,
                    inputStyle={"marginRight": "4px", "marginLeft": "8px"},
                ),
                style={"marginBottom": "8px", "fontSize": "13px"},
            ),
            html.Div(id="sit-lights", style=theme.ROW),
            html.Div(
                [
                    html.Div(
                        [
                            heading(
                                f"What changed in the last {days} days",
                                "Chokepoints newly below "
                                f"{data.monitor_config.disruption_threshold:.0%} of normal, new "
                                "orange or red "
                                "disruption events, gale or storm forecasts and the largest "
                                f"{days}-day moves of daily market series. 'Relevant for "
                                "Europe' keeps only the supplier regions, sea routes, ports and "
                                "series that matter for European PE imports.",
                            ),
                            html.Div(id="sit-changes"),
                        ],
                        style=card,
                    ),
                    html.Div(
                        [
                            heading(
                                "Chokepoints furthest below normal (all vessels)",
                                "7-day average of all transits against the same calendar week "
                                "2019-2023 (IMF PortWatch). Second line: share of Europe's PE "
                                "imports from outside Europe whose sea route passes it (a "
                                "range where a country's export port is not known), and what a "
                                "closure would mean: extra days at sea on the chokepoint's own "
                                "detour (searoute, "
                                f"{data.sourcing_config.lead_time.speed:g} knots: average speed "
                                "at sea of container ships, Fourth IMO GHG Study 2020), or no "
                                "sea detour (e.g. Hormuz) – then the supply is at risk.",
                            ),
                            html.Div(id="sit-chokepoints"),
                        ],
                        style=card,
                    ),
                ],
                style=theme.ROW,
            ),
            html.Div(
                [
                    heading(
                        "Active disruption events (IMF PortWatch, orange and red alerts)",
                        "Open events and events that ended in the last 30 days. 'Relevant for "
                        "Europe': within "
                        f"{data.sourcing_config.relevance.event_radius_km:,.0f} km of a relevant "
                        "chokepoint or port.",
                    ),
                    html.Div(id="sit-events"),
                ],
                style=theme.CARD,
            ),
        ]
    )


def sparkline(frame: pd.DataFrame, colour: str) -> dcc.Graph:
    fig = go.Figure(
        go.Scatter(
            x=frame["date"],
            y=frame["value"],
            line={"color": colour, "width": 1.5},
            hovertemplate="%{x|%d %b %Y}: %{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=60,
        margin={"l": 0, "r": 0, "t": 4, "b": 0},
        paper_bgcolor=theme.SURFACE,
        plot_bgcolor=theme.SURFACE,
        showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def action_link(title: str) -> html.Button:
    """A link-styled button; the navigation callback (app.__main__) opens the tab."""
    text, tab = ACTIONS[title]
    return html.Button(
        text,
        id={"type": "goto", "tab": tab},
        n_clicks=0,
        style={
            "background": "none",
            "border": "none",
            "padding": "0",
            "color": theme.BLUE,
            "cursor": "pointer",
            "fontSize": "13px",
            "fontWeight": "600",
        },
    )


def light_card(
    signal: signals.Signal, note: str, trend: pd.DataFrame | None, level: str | None
) -> html.Div:
    """One card: title + (i), level (icon and word), value, note, sparkline, action link.

    `level` None = an indicator without a traffic light (the polyethylene card).
    """
    if level is None:
        badge: Component = html.Span("indicator", style={"fontSize": "12px", "color": theme.MUTED})
        colour = theme.GRID
    else:
        icon, word, colour = LEVELS[level]
        badge = html.Span(
            f"{icon} {word}", style={"color": colour, "fontWeight": "600", "fontSize": "13px"}
        )
    children: list[Component] = [
        html.Div(
            [
                html.Span(
                    [signal.title, info(note)], style={"fontSize": "13px", "color": theme.MUTED}
                ),
                badge,
            ],
            style={"display": "flex", "justifyContent": "space-between"},
        ),
        html.Div(signal.value, style={"fontSize": "26px", "fontWeight": "600"}),
        html.Div(signal.note, style={"fontSize": "11px", "color": theme.MUTED}),
    ]
    if trend is not None and not trend.empty:
        children.append(sparkline(trend, theme.BLUE))
    children.append(html.Div(action_link(signal.title), style={"marginTop": "4px"}))
    return html.Div(
        children,
        style={
            **theme.CARD,
            "flex": "1",
            "minWidth": "230px",
            "borderTop": f"4px solid {colour}",
            "borderRadius": "0 0 8px 8px",
        },
    )


def steps(threshold: Threshold, unit: str) -> str:
    return (
        f"watch from {threshold.yellow:g}{unit}, elevated from {threshold.orange:g}{unit}, "
        f"critical from {threshold.red:g}{unit}"
    )


def light_notes(data: AppData) -> dict[str, str]:
    """Tooltip texts of the cards, with the thresholds from config/sourcing.yaml."""
    s = data.sourcing_config.signals
    return {
        "Price": f"Brent in EUR, change over {s.price.days} days ({steps(s.price, ' %')}). "
        "Feedstock cost of naphtha-based European crackers.",
        "Supply": "Share of Europe's PE imports from outside Europe (BACI, latest year) whose "
        f"sea route passes a chokepoint flagged disrupted today ({steps(s.supply, ' %')}).",
        "Logistics": "NY Fed Global Supply Chain Pressure Index, standard deviations from the "
        f"average ({steps(s.logistics, '')}; its 2021 peak was 4.3).",
        "Polyethylene": "LLDPE futures, Dalian (China, incl. VAT), converted to EUR: the only "
        "free daily PE price; an indicator of the Asian market, not a European price. Without "
        "it: the US price index for plastics resins (monthly).",
    }


def pe_signal(data: AppData) -> tuple[signals.Signal, pd.DataFrame | None]:
    """Polyethylene indicator: Dalian LLDPE in EUR (7-day change), else the US resin index."""
    title = "Polyethylene"
    market = data.market
    if market is None:
        return signals.Signal(title, signals.GREEN, "n/a", "no market data yet"), None
    dce = prices.dce_in_currency(market, "EUR")
    if not dce.empty:
        last = dce.iloc[-1]
        earlier = dce[dce["date"] <= last["date"] - pd.Timedelta(days=7)]
        change = None if earlier.empty else (last["value"] / earlier.iloc[-1]["value"] - 1) * 100
        note = f"LLDPE Dalian, {charts.signed_pct(change)} in 7 days · {last['date']:%d %b}"
        trend = dce[dce["date"] > last["date"] - pd.Timedelta(days=365)]
        value = f"{last['value']:,.0f} EUR/t"
        return signals.Signal(title, signals.GREEN, value, note), trend
    resin = indicators.series(market, "PCU325211325211")
    if resin.empty:
        return signals.Signal(title, signals.GREEN, "n/a", "no PE price yet"), None
    change = indicators.change_pct(market, "PCU325211325211", 28)
    note = f"US resin price index, {charts.signed_pct(change)} vs. last month"
    value = f"{resin['value'].iloc[-1]:,.0f}"
    return signals.Signal(title, signals.GREEN, value, note), resin.tail(24)


def _bullets(items: list[Component]) -> Component:
    if not items:
        return html.Div("● Nothing new", style={"color": theme.GOOD})
    return html.Ul(
        [html.Li(i, style={"fontSize": "14px", "marginBottom": "4px"}) for i in items],
        style={"paddingLeft": "18px", "margin": "0"},
    )


def relevant_points(data: AppData, scope: str) -> pd.DataFrame | None:
    """Coordinates of the relevant chokepoints and ports; None = no filter."""
    rel = data.relevance
    if scope == ALL or rel is None:
        return None
    chokepoints = data.chokepoints[data.chokepoints["chokepoint_id"].isin(rel.chokepoints)]
    frames = [chokepoints[["lat", "lon"]]]
    if data.ports is not None:
        frames.append(data.ports[data.ports["port_id"].isin(rel.ports)][["lat", "lon"]])
    return pd.concat(frames, ignore_index=True)


def filter_events(events: pd.DataFrame, data: AppData, scope: str) -> pd.DataFrame:
    points = relevant_points(data, scope)
    if points is None or events.empty:
        return events
    radius = data.sourcing_config.relevance.event_radius_km
    return events[relevance.near_any(events, points, radius)]


def change_items(data: AppData, scope: str, today: pd.Timestamp | None = None) -> list[Component]:
    days = data.sourcing_config.recent_days
    rel = data.relevance if scope == EUROPE else None
    items: list[Component] = []
    newly = signals.newly_disrupted(data.chokepoint_history, days)
    if rel is not None:
        newly = newly[newly["location_id"].isin(rel.chokepoints)]
    for row in newly.to_dict("records"):
        items.append(
            html.Span(
                [
                    html.Span(f"▼ {row['location']}", style={"color": theme.CRITICAL}),
                    f" newly below normal ({fmt.pct(row['deviation_pct'])})",
                ]
            )
        )
    if data.events is not None:
        new = signals.new_events(data.events, data.latest_date, days)
        for event in filter_events(new, data, scope).to_dict("records"):
            items.append(
                html.Span(
                    [
                        html.Span(f"▲ {event['alert_level']} ", style={"color": theme.CRITICAL}),
                        f"new event: {event['event']} (from {event['from_date']:%d %b})",
                    ]
                )
            )
    if data.weather is not None:
        now = today if today is not None else pd.Timestamp(pd.Timestamp.now(tz="UTC").date())
        warnings = storm_warnings(data.weather, now, data.monitor_config.weather)
        if rel is not None:
            warnings = warnings[warnings["location_id"].isin(rel.chokepoints | rel.ports)]
        for row in warnings.drop_duplicates("location_id").head(5).to_dict("records"):
            storm = row["level"] == "red"
            kind, colour = ("Storm", theme.CRITICAL) if storm else ("Gale", theme.WARNING)
            items.append(
                html.Span(
                    [
                        html.Span(f"▲ {kind} forecast ", style={"color": colour}),
                        f"at {row['location']} on {row['date']:%d %b}: "
                        + weather_text(row["wave_height_m"], row["wind_gusts_kmh"]),
                    ]
                )
            )
    if data.market is not None:
        series = rel.series if rel is not None else None
        moves = signals.largest_moves(data.market, days=days, series_ids=series)
        for move in moves.to_dict("records"):
            arrow = "▲" if move["change_pct"] > 0 else "▼"
            text = f"{arrow} {move['name']}: {fmt.pct(move['change_pct'])} in {days} days"
            items.append(html.Span(text))
    return items


def weather_text(waves_m: float | None, gusts_kmh: float | None) -> str:
    """'waves 1.4 m, gusts 69 km/h'; parts without data are left out (no waves on land)."""
    parts = []
    if waves_m is not None and not pd.isna(waves_m):
        parts.append(f"waves {waves_m:.1f} m")
    if gusts_kmh is not None and not pd.isna(gusts_kmh):
        parts.append(f"gusts {gusts_kmh:,.0f} km/h")
    return ", ".join(parts)


def chokepoint_list(data: AppData, scope: str) -> Component:
    flagged = furthest_below_normal(latest_status(data.chokepoint_history), n=10)
    rel = data.relevance if scope == EUROPE else None
    if rel is not None:
        flagged = flagged[flagged["location_id"].isin(rel.chokepoints)]
    flagged = flagged.head(5)
    if flagged.empty:
        return html.Div("● None flagged", style={"color": theme.GOOD})
    dependency = data.chokepoint_dependency
    details = {} if dependency is None else dependency.set_index("chokepoint_id").to_dict("index")
    items = []
    for row in flagged.to_dict("records"):
        detail = details.get(row["location_id"])
        if detail is None:
            text = "no European PE imports on this route"
        else:
            share = signals.pct_range(detail["share_low_pct"], detail["share_pct"])
            text = f"{share} of Europe's PE imports from outside Europe"
            extra = detail["extra_days"]
            if not detail["has_detour"]:
                text += " · no sea detour – supply at risk if closed"
            elif extra is not None and not pd.isna(extra):
                text += f" · if closed: +{extra:.0f} days at sea on the detour"
        items.append(
            html.Li(
                [
                    html.Span(f"▼ {row['location']}", style={"color": theme.CRITICAL}),
                    f"  {fmt.pct(row['deviation_pct'])} vs. normal",
                    html.Div(text, style={"fontSize": "12px", "color": theme.MUTED}),
                ],
                title=text,
                style={"fontSize": "14px", "marginBottom": "6px"},
            )
        )
    return html.Ul(items, style={"paddingLeft": "18px", "margin": "0"})


def _event_list(events: pd.DataFrame) -> Component:
    items: list[Component] = []
    for event in events.to_dict("records"):
        kind = EVENT_TYPES.get(event["event_type"], event["event_type"])
        since = f"since {event['from_date']:%d %b %Y}" + (
            "" if pd.isna(event["to_date"]) else f", until {event['to_date']:%d %b %Y}"
        )
        items.append(
            html.Span(
                [
                    html.Span(
                        f"▲ {event['alert_level']} ",
                        style={"color": theme.CRITICAL, "fontWeight": "600"},
                    ),
                    f"{event['event']} ({kind}), {since}",
                ]
            )
        )
    return _bullets(items)


def update(
    data: AppData,
    scope: str = EUROPE,
    today: pd.Timestamp | None = None,
    scenario: str = LIVE,
) -> charts.Outputs:
    lights = traffic_lights(
        data.market, data.sourcing_for(ALL_GRADES, scenario), data.sourcing_config
    )
    notes = light_notes(data)
    trends: list[pd.DataFrame | None] = [None, None, None]
    if data.market is not None:
        latest = data.market["date"].max()
        price_id = data.sourcing_config.signals.price.series
        eur = indicators.series(indicators.in_currency(data.market, "EUR"), price_id)
        trends[0] = eur[eur["date"] > latest - pd.Timedelta(days=365)]
        gscpi = indicators.series(data.market, data.sourcing_config.signals.logistics.series)
        trends[2] = gscpi.tail(24)
    cards = [light_card(s, notes[s.title], t, s.level) for s, t in zip(lights, trends, strict=True)]
    pe, pe_trend = pe_signal(data)
    cards.append(light_card(pe, notes["Polyethylene"], pe_trend, None))

    events: Component = html.Div("No event data yet.", style={"color": theme.MUTED})
    if data.events is not None:
        active = active_events(data.events, data.latest_date)
        events = _event_list(filter_events(active, data, scope))
    return cards, _bullets(change_items(data, scope, today)), chokepoint_list(data, scope), events


def register(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("sit-lights", "children"),
        Output("sit-changes", "children"),
        Output("sit-chokepoints", "children"),
        Output("sit-events", "children"),
        Input("sit-scope", "value"),
        Input("scenario", "value"),
        Input("data-version", "data"),
    )
    def _update(scope: str, scenario: str, _version: int) -> charts.Outputs:
        return update(state.data, scope, scenario=scenario)
