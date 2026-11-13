"""Start the app: `uv run python -m ptf.app` and open http://127.0.0.1:8050

In the container gunicorn serves the same app (`ptf.app.wsgi`, ADR-013).

The page has a header (title, data status, update button) and one tab per topic. Each tab
module provides `layout(data)` and `register(app, state)`; the callbacks only pass values
to functions in `src/ptf/` and `ptf.app.charts`.
"""

from dash import Dash, Input, Output, State, dcc, html

from ptf.app import style
from ptf.app.data import AppState, monitor_data_available
from ptf.app.tabs import chokepoints, flows, markets, overview, ports
from ptf.core.settings import Settings, get_settings

TABS = [
    ("overview", "Overview", overview),
    ("chokepoints", "Chokepoints", chokepoints),
    ("ports", "Ports", ports),
    ("flows", "Trade flows", flows),
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


def no_data_layout() -> html.Div:
    """Shown instead of the tabs while the warehouse has no shipping data (e.g. fresh clone)."""
    return html.Div(
        [
            html.H1("Shipping & market monitor", style={"fontSize": "22px"}),
            html.P("No data yet. Build the warehouse, then restart the app:"),
            html.Pre(
                "uv run ptf portwatch   # chokepoints, ports, events\n"
                "uv run ptf market      # energy, freight and supply-chain series",
            ),
        ],
        id="no-data",
        style=style.PAGE,
    )


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
    settings = settings or get_settings()
    app = Dash(__name__, title="Shipping & market monitor")
    if not monitor_data_available(settings):
        app.layout = no_data_layout()
        return app
    state = AppState(settings)
    app.layout = build_layout(state)
    for _, _, module in TABS:
        module.register(app, state)
    register_refresh(app, state)
    return app


def main() -> None:
    settings = get_settings()
    create_app(settings).run(host=settings.app_host, port=settings.app_port, debug=False)


if __name__ == "__main__":
    main()
