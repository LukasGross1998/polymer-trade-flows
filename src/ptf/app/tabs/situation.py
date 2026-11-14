"""Tab "Situation": do I need to act today? Three traffic lights and what changed."""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html
from dash.development.base_component import Component

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.insights import signals
from ptf.insights.view import traffic_lights
from ptf.markets import indicators
from ptf.shipping.metrics import latest_status
from ptf.shipping.overview import active_events, furthest_below_normal
from ptf.shipping.vocabulary import EVENT_TYPES
from ptf.shipping.weather import storm_warnings

# Icon + word + colour, never colour alone.
LEVELS = {
    signals.GREEN: ("●", "OK", style.GOOD),
    signals.AMBER: ("▲", "Watch", style.WARNING),
    signals.RED: ("▲", "Act", style.CRITICAL),
}


def layout(data: AppData) -> html.Div:
    card = {**style.CARD, "flex": "1", "minWidth": "300px"}
    return html.Div(
        [
            html.Div(id="sit-lights", style=style.ROW),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                f"What changed in the last {data.sourcing_config.recent_days} days",
                                style=style.SECTION_TITLE,
                            ),
                            html.Div(id="sit-changes"),
                        ],
                        style=card,
                    ),
                    html.Div(
                        [
                            html.Div(
                                "Chokepoints furthest below normal (all vessels)",
                                style=style.SECTION_TITLE,
                            ),
                            html.Div(id="sit-chokepoints"),
                        ],
                        style=card,
                    ),
                ],
                style=style.ROW,
            ),
            html.Div(
                [
                    html.Div(
                        "Active disruption events (IMF PortWatch, orange and red alerts)",
                        style=style.SECTION_TITLE,
                    ),
                    html.Div(id="sit-events"),
                ],
                style=style.CARD,
            ),
            html.Div(
                "Thresholds of the traffic lights: config/sourcing.yaml (assumptions). "
                "Price: Brent in EUR, change over 90 days. Supply: share of imports from outside "
                "Europe whose sea route passes a chokepoint flagged disrupted today (see "
                "Sourcing). Logistics: NY Fed Global Supply Chain Pressure Index.",
                style=style.SMALL_NOTE,
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
        paper_bgcolor=style.SURFACE,
        plot_bgcolor=style.SURFACE,
        showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "staticPlot": False})


def light_card(signal: signals.Signal, trend: pd.DataFrame | None) -> html.Div:
    icon, word, colour = LEVELS[signal.level]
    children: list[Component] = [
        html.Div(
            [
                html.Span(signal.title, style={"fontSize": "13px", "color": style.MUTED}),
                html.Span(
                    f"{icon} {word}",
                    style={"color": colour, "fontWeight": "600", "fontSize": "13px"},
                ),
            ],
            style={"display": "flex", "justifyContent": "space-between"},
        ),
        html.Div(signal.value, style={"fontSize": "26px", "fontWeight": "600"}),
        html.Div(signal.note, style={"fontSize": "11px", "color": style.MUTED}),
    ]
    if trend is not None and not trend.empty:
        children.append(sparkline(trend, style.BLUE))
    return html.Div(
        children,
        style={
            **style.CARD,
            "flex": "1",
            "minWidth": "260px",
            "borderTop": f"4px solid {colour}",
            "borderRadius": "0 0 8px 8px",
        },
    )


def _bullets(items: list[Component]) -> Component:
    if not items:
        return html.Div("● Nothing new", style={"color": style.GOOD})
    return html.Ul(
        [html.Li(i, style={"fontSize": "14px", "marginBottom": "4px"}) for i in items],
        style={"paddingLeft": "18px", "margin": "0"},
    )


def change_items(data: AppData) -> list[Component]:
    days = data.sourcing_config.recent_days
    items: list[Component] = []
    for row in signals.newly_disrupted(data.chokepoint_history, days).to_dict("records"):
        items.append(
            html.Span(
                [
                    html.Span(f"▼ {row['location']}", style={"color": style.CRITICAL}),
                    f" newly below normal ({row['deviation_pct']:+.0f} %)",
                ]
            )
        )
    if data.events is not None:
        for event in signals.new_events(data.events, data.latest_date, days).to_dict("records"):
            items.append(
                html.Span(
                    [
                        html.Span(f"▲ {event['alert_level']} ", style={"color": style.CRITICAL}),
                        f"new event: {event['event']} (from {event['from_date']:%d %b})",
                    ]
                )
            )
    if data.weather is not None:
        today = pd.Timestamp(pd.Timestamp.now(tz="UTC").date())
        warnings = storm_warnings(data.weather, today, data.monitor_config.weather)
        for row in warnings.drop_duplicates("location_id").head(5).to_dict("records"):
            kind = "Storm" if row["level"] == "red" else "Gale"
            colour = style.CRITICAL if row["level"] == "red" else style.WARNING
            items.append(
                html.Span(
                    [
                        html.Span(f"▲ {kind} forecast ", style={"color": colour}),
                        f"at {row['location']} on {row['date']:%d %b}: waves "
                        f"{charts.number(row['wave_height_m'])} m, gusts "
                        f"{charts.number(row['wind_gusts_kmh'], ',.0f')} km/h",
                    ]
                )
            )
    if data.market is not None:
        for move in signals.largest_moves(data.market, days=30).to_dict("records"):
            arrow = "▲" if move["change_pct"] > 0 else "▼"
            text = f"{arrow} {move['name']}: {move['change_pct']:+.1f} % in 30 days"
            items.append(html.Span(text))
    return items


def _location_list(rows: pd.DataFrame) -> Component:
    return _bullets(
        [
            html.Span(
                [
                    html.Span(f"▼ {row['location']}", style={"color": style.CRITICAL}),
                    f"  {row['deviation_pct']:+.0f} % vs. normal",
                ]
            )
            for row in rows.to_dict("records")
        ]
    )


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
                        style={"color": style.CRITICAL, "fontWeight": "600"},
                    ),
                    f"{event['event']} ({kind}), {since}",
                ]
            )
        )
    return _bullets(items)


def update(data: AppData) -> charts.Outputs:
    lights = traffic_lights(data.market, data.sourcing, data.sourcing_config)
    trends: list[pd.DataFrame | None] = [None, None, None]
    if data.market is not None:
        latest = data.market["date"].max()
        price_id = data.sourcing_config.signals.price.series
        eur = indicators.series(indicators.in_currency(data.market, "EUR"), price_id)
        trends[0] = eur[eur["date"] > latest - pd.Timedelta(days=365)]
        gscpi = indicators.series(data.market, data.sourcing_config.signals.logistics.series)
        trends[2] = gscpi.tail(24)
    cards = [light_card(s, t) for s, t in zip(lights, trends, strict=True)]

    chokepoints = latest_status(data.chokepoint_history)
    events: Component = html.Div("No event data yet.", style={"color": style.MUTED})
    if data.events is not None:
        events = _event_list(active_events(data.events, data.latest_date))
    return (
        cards,
        _bullets(change_items(data)),
        _location_list(furthest_below_normal(chokepoints)),
        events,
    )


def register(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("sit-lights", "children"),
        Output("sit-changes", "children"),
        Output("sit-chokepoints", "children"),
        Output("sit-events", "children"),
        Input("data-version", "data"),
    )
    def _update(_version: int) -> charts.Outputs:
        return update(state.data)
