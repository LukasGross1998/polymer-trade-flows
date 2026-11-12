"""Start the app: `uv run python -m ptf.app` and open http://127.0.0.1:8050"""

from dash import Dash

from ptf.app.callbacks import register_callbacks
from ptf.app.data import AppState
from ptf.app.layout import build_layout
from ptf.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> Dash:
    state = AppState(settings or get_settings())
    app = Dash(__name__, title="Shipping chokepoint monitor")
    app.layout = build_layout(state.data)
    register_callbacks(app, state)
    return app


def main() -> None:
    create_app().run(host="127.0.0.1", port=8050, debug=False)


if __name__ == "__main__":
    main()
