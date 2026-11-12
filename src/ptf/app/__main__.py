"""Start the app: `uv run python -m ptf.app` and open http://127.0.0.1:8050

The page has a header (title, data status, update button) and one tab per topic. Each tab
module provides `layout(data)` and `register(app, state)`; the callbacks only pass values
to functions in `src/ptf/` and `ptf.app.charts`.
"""

from dash import Dash, Input, Output, State, dcc, html

from ptf.app import style
from ptf.app.data import AppState
from ptf.app.tabs import chokepoints, markets, overview, ports
from ptf.config import Settings, get_settings

TABS = [
    ("overview", "Overview", overview),
    ("chokepoints", "Chokepoints", chokepoints),
    ("ports", "Ports", ports),
    ("markets", "Energy & freight", markets),
]


def build_layout(state: AppState) -> html.Div:
    header = html.Div(
        [
            html.Div(
                [
                    html.H1("Shipping & market monitor", style={"fontSize": "22px", "margin": "0"}),
                    html.Div(
                        "Chokepoints, ports, energy and freight: what moves polyethylene trade",
                        style={"fontSize": "13px", "color": style.INK_SECONDARY},
                    ),
                ]
            ),
            html.Div(
                [
                    html.Button("Update data", id="refresh", n_clicks=0),
                    html.Div(id="refresh-status", style={"fontSize": "12px", "color": style.MUTED}),
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
    tabs = dcc.Tabs(
        [
            dcc.Tab(
                label=label,
                value=value,
                children=html.Div(module.layout(state.data), style={"paddingTop": "16px"}),
            )
            for value, label, module in TABS
        ],
        value="overview",
    )
    return html.Div([header, tabs, dcc.Store(id="data-version", data=0)], style=style.PAGE)


def register_refresh(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("refresh-status", "children"),
        Output("data-version", "data"),
        Input("refresh", "n_clicks"),
        State("data-version", "data"),
        prevent_initial_call=True,
    )
    def _refresh(_clicks: int, version: int) -> tuple[str, int]:
        new_days = state.refresh()
        return f"Updated: {new_days} new day(s) of chokepoint data", version + 1


def create_app(settings: Settings | None = None) -> Dash:
    state = AppState(settings or get_settings())
    app = Dash(__name__, title="Shipping & market monitor")
    app.layout = build_layout(state)
    for _, _, module in TABS:
        module.register(app, state)
    register_refresh(app, state)
    return app


def main() -> None:
    create_app().run(host="127.0.0.1", port=8050, debug=False)


if __name__ == "__main__":
    main()
