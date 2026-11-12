"""Page structure of the app (Dash components). No data processing here."""

from dash import dcc, html

from ptf.app.data import MonitorData
from ptf.app.figures import INK, INK_SECONDARY, MUTED, PERIOD_LABELS, SURFACE, VESSEL_LABELS

PAGE = {
    "fontFamily": "-apple-system, 'Segoe UI', Roboto, sans-serif",
    "backgroundColor": "#f9f9f7",
    "color": INK,
    "padding": "16px 24px",
    "maxWidth": "1280px",
    "margin": "0 auto",
}
CARD = {
    "backgroundColor": SURFACE,
    "border": "1px solid #e1e0d9",
    "borderRadius": "8px",
    "padding": "12px 16px",
}
CONTROL = {"minWidth": "220px", "flex": "1"}

DEFAULT_CHOKEPOINT = "chokepoint4"  # Bab el-Mandeb: the Red Sea crisis is the reference case
DEFAULT_VESSEL_TYPE = "container"
DEFAULT_PERIOD = "3y"


def _control(label: str, component: object) -> html.Div:
    return html.Div(
        [html.Label(label, style={"fontSize": "12px", "color": MUTED}), component], style=CONTROL
    )


def build_layout(data: MonitorData) -> html.Div:
    chokepoint_options = [
        {"label": row.chokepoint, "value": row.chokepoint_id}
        for row in data.chokepoints.sort_values("chokepoint").itertuples()
    ]
    controls = html.Div(
        [
            _control(
                "Chokepoint (or click on the map)",
                dcc.Dropdown(
                    id="chokepoint",
                    options=chokepoint_options,
                    value=DEFAULT_CHOKEPOINT,
                    clearable=False,
                ),
            ),
            _control(
                "Vessel type",
                dcc.Dropdown(
                    id="vessel-type",
                    options=[
                        {"label": v.capitalize(), "value": k} for k, v in VESSEL_LABELS.items()
                    ],
                    value=DEFAULT_VESSEL_TYPE,
                    clearable=False,
                ),
            ),
            _control(
                "Period",
                dcc.Dropdown(
                    id="period",
                    options=[{"label": v, "value": k} for k, v in PERIOD_LABELS.items()],
                    value=DEFAULT_PERIOD,
                    clearable=False,
                ),
            ),
        ],
        style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "16px"},
    )

    header = html.Div(
        [
            html.Div(
                [
                    html.H1(
                        "Shipping chokepoint monitor", style={"fontSize": "22px", "margin": "0"}
                    ),
                    html.Div(id="freshness", style={"fontSize": "13px", "color": INK_SECONDARY}),
                ]
            ),
            html.Div(
                [
                    html.Button("Update data", id="refresh", n_clicks=0),
                    html.Div(id="refresh-status", style={"fontSize": "12px", "color": MUTED}),
                ],
                style={"textAlign": "right"},
            ),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "start",
            "marginBottom": "12px",
        },
    )

    return html.Div(
        [
            header,
            controls,
            html.Div(
                id="kpis",
                style={
                    "display": "flex",
                    "gap": "12px",
                    "flexWrap": "wrap",
                    "marginBottom": "16px",
                },
            ),
            html.Div(dcc.Graph(id="map", config={"displayModeBar": False}), style=CARD),
            html.Div(
                [
                    html.Div(
                        dcc.Graph(id="timeseries"), style={**CARD, "flex": "1", "minWidth": "420px"}
                    ),
                    html.Div(
                        [
                            html.Div(
                                "Red Sea diversion: container ships between Asia and Europe",
                                style={"fontWeight": "600", "fontSize": "14px"},
                            ),
                            dcc.Graph(id="diversion"),
                        ],
                        style={**CARD, "flex": "1", "minWidth": "420px"},
                    ),
                ],
                style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginTop": "16px"},
            ),
            html.Div(
                "Source: IMF PortWatch (daily transit counts from satellite AIS data). "
                "Not real-time: data arrive a few days late and are updated about weekly. "
                "Normal = average of the same calendar week in 2019-2023. Chokepoints with "
                "less than 2 vessels a day of normal traffic are never flagged as disrupted.",
                style={"fontSize": "12px", "color": MUTED, "marginTop": "12px"},
            ),
            dcc.Store(id="data-version", data=0),
        ],
        style=PAGE,
    )


def kpi_tiles(values: list[dict]) -> list[html.Div]:
    """Stat tiles from `figures.kpis`; text stays in ink colours, tone only on the status value."""
    tiles = []
    for item in values:
        value_style = {"fontSize": "24px", "fontWeight": "600", "color": item.get("tone", INK)}
        tiles.append(
            html.Div(
                [
                    html.Div(item["label"], style={"fontSize": "12px", "color": MUTED}),
                    html.Div(item["value"], style=value_style),
                ],
                style={**CARD, "flex": "1", "minWidth": "200px"},
            )
        )
    return tiles
