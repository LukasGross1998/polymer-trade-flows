"""Start the app: `uv run python -m ptf.app` and open http://127.0.0.1:8050

In the container gunicorn serves the same app (`ptf.app.wsgi`, ADR-013).

The page has a header (title, data status, update button) and one tab per topic. Each tab
module provides `layout(data)` and `register(app, state)`; the callbacks only pass values
to functions in `src/ptf/` and `ptf.app.charts`.
"""

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update

from ptf.app import style
from ptf.app.data import AppData, AppState, monitor_data_available
from ptf.app.tabs import (
    chokepoints,
    classes,
    flows,
    landed_cost,
    planner,
    ports,
    prices,
    situation,
    sourcing,
)
from ptf.core.settings import Settings, get_settings
from ptf.insights.scenario import LIVE

# Two sections (spec 008): the buyer's questions first, market and logistics detail after.
SECTIONS = [
    (
        "buying",
        "Buying",
        [
            ("situation", "Situation", situation),
            ("prices", "Prices & drivers", prices),
            ("sourcing", "Sourcing", sourcing),
            ("landed", "Landed cost", landed_cost),
            ("planner", "Order planner", planner),
        ],
    ),
    (
        "markets",
        "Markets & logistics",
        [
            ("classes", "World trade by class", classes),
            ("chokepoints", "Chokepoints", chokepoints),
            ("ports", "Ports", ports),
            ("flows", "Trade flows", flows),
        ],
    ),
]
TABS = [tab for _, _, tabs in SECTIONS for tab in tabs]

SECTION_TAB = {"fontWeight": "600", "padding": "8px 16px"}


def build_layout(state: AppState) -> html.Div:
    header = html.Div(
        [
            html.Div(
                [
                    html.H1(
                        "Polyethylene supply chain monitor",
                        style={"fontSize": "22px", "margin": "0"},
                    ),
                    html.Div(
                        "For buyers in Europe: prices, sourcing risk, chokepoints and ports",
                        style={"fontSize": "13px", "color": style.INK_SECONDARY},
                    ),
                ]
            ),
            html.Div(
                [
                    html.Div("Route scenario", style={"fontSize": "12px", "color": style.MUTED}),
                    dcc.Dropdown(
                        id="scenario",
                        options=state.data.scenario_options(),
                        value=LIVE,
                        clearable=False,
                        persistence=True,
                        style={"width": "220px", "fontSize": "13px"},
                    ),
                ],
                title=(
                    "Applies to all tabs. Live status: a chokepoint counts as closed when its "
                    "7-day traffic is at least "
                    f"{state.data.sourcing_config.scenarios.closed_below_pct:g} % below normal "
                    "(IMF PortWatch), as reduced when the monitor flags it."
                ),
            ),
            html.Div(
                [
                    html.Button("Update data", id="refresh", n_clicks=0),
                    html.Div(
                        freshness(state.data),
                        id="last-updated",
                        style={"fontSize": "12px", "color": style.MUTED, "marginTop": "4px"},
                    ),
                    html.Div(id="refresh-status", style={"fontSize": "12px", "color": style.MUTED}),
                ],
                style={"textAlign": "right"},
            ),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "start",
            "gap": "16px",
            "marginBottom": "12px",
        },
    )
    sections = [
        dcc.Tab(
            label=section_label,
            value=section_id,
            style=SECTION_TAB,
            selected_style=SECTION_TAB,
            children=dcc.Tabs(
                id=f"tabs-{section_id}",
                children=[
                    dcc.Tab(
                        label=label,
                        value=value,
                        children=html.Div(module.layout(state.data), style={"paddingTop": "16px"}),
                    )
                    for value, label, module in tabs
                ],
                value=tabs[0][0],
                style={"marginTop": "8px"},
            ),
        )
        for section_id, section_label, tabs in SECTIONS
    ]
    tabs = dcc.Tabs(sections, id="section-tabs", value="buying")
    return html.Div([header, tabs, dcc.Store(id="data-version", data=0)], style=style.PAGE)


def no_data_layout() -> html.Div:
    """Shown instead of the tabs while the warehouse has no shipping data (e.g. fresh clone)."""
    return html.Div(
        [
            html.H1("Polyethylene supply chain monitor", style={"fontSize": "22px"}),
            html.P("No data yet. Build the warehouse, then restart the app:"),
            html.Pre(
                "uv run ptf portwatch   # chokepoints, ports, events\n"
                "uv run ptf market      # energy, freight and supply-chain series",
            ),
        ],
        id="no-data",
        style=style.PAGE,
    )


def freshness(data: AppData) -> str:
    """'Last updated' (time of the last warehouse build) and the newest data dates."""
    parts = []
    if data.updated_at is not None:
        local = data.updated_at.tz_convert("Europe/Berlin")
        parts.append(f"Last updated: {local:%d %b %Y, %H:%M}")
    parts.append(f"chokepoints to {data.latest_date:%d %b}")
    if data.market is not None:
        parts.append(f"markets to {data.market['date'].max():%d %b}")
    return " · ".join(parts)


# Sub-tab -> section, for the action links on the situation page (spec 013).
TAB_SECTION = {value: section_id for section_id, _, tabs in SECTIONS for value, _, _ in tabs}


def navigate(tab: str) -> tuple[object, ...]:
    """Values of the section tabs and every section's sub-tabs that show `tab`.

    Sections that do not contain `tab` keep their current sub-tab (no_update).
    """
    section = TAB_SECTION[tab]
    values: list[object] = [section]
    for section_id, _, _ in SECTIONS:
        values.append(tab if section_id == section else no_update)
    return tuple(values)


def register_navigation(app: Dash) -> None:
    @app.callback(
        Output("section-tabs", "value"),
        *[Output(f"tabs-{section_id}", "value") for section_id, _, _ in SECTIONS],
        Input({"type": "goto", "tab": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def _goto(clicks: list[int | None]) -> tuple[object, ...]:
        # Cards are rebuilt by callbacks; their new buttons (n_clicks 0) must not navigate.
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not any(clicks):
            return tuple(no_update for _ in range(len(SECTIONS) + 1))
        return navigate(str(trigger["tab"]))


def register_refresh(app: Dash, state: AppState) -> None:
    @app.callback(
        Output("refresh-status", "children"),
        Output("data-version", "data"),
        Output("last-updated", "children"),
        Input("refresh", "n_clicks"),
        State("data-version", "data"),
        prevent_initial_call=True,
    )
    def _refresh(_clicks: int, version: int) -> tuple[str, int, str]:
        new_days = state.refresh()
        message = f"Updated: {new_days} new day(s) of chokepoint data"
        return message, version + 1, freshness(state.data)


def create_app(settings: Settings | None = None) -> Dash:
    settings = settings or get_settings()
    app = Dash(__name__, title="Polyethylene supply chain monitor")
    if not monitor_data_available(settings):
        app.layout = no_data_layout()
        return app
    state = AppState(settings)
    app.layout = build_layout(state)
    for _, _, module in TABS:
        module.register(app, state)
    register_refresh(app, state)
    register_navigation(app)
    return app


def main() -> None:
    settings = get_settings()
    create_app(settings).run(host=settings.app_host, port=settings.app_port, debug=False)


if __name__ == "__main__":
    main()
