"""Tab "Energy & freight": oil, gas, freight and polymer price proxies, supply-chain stress."""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, html

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.market import indicators

INDEXED_GROUPS = {
    "freight_polymers": "Freight and polymer prices (US producer price indices)",
    "fx": "Exchange rates",
}


def layout(data: AppData) -> html.Div:
    if data.market is None:
        return charts.no_data("No market data yet: run `uv run python -m ptf.pipeline market`.")
    card = {**style.CARD, "flex": "1", "minWidth": "420px"}
    return html.Div(
        [
            html.Div(
                charts.control("Period", charts.period_dropdown("mkt-period", "5y")),
                style=style.ROW,
            ),
            html.Div(id="mkt-kpis", style=style.ROW),
            html.Div(
                [
                    html.Div(charts.graph("mkt-oil"), style=card),
                    html.Div(charts.graph("mkt-gas"), style=card),
                ],
                style=style.ROW,
            ),
            html.Div(
                [
                    html.Div(charts.graph("mkt-indexed"), style=card),
                    html.Div(charts.graph("mkt-gscpi"), style=card),
                ],
                style=style.ROW,
            ),
            html.Div(
                "Sources: FRED (St. Louis Fed): Brent, WTI, Henry Hub (daily); natural gas Europe "
                "and LNG Japan (IMF, monthly); US producer price indices for deep sea freight and "
                "thermoplastic resins (BLS, monthly) as proxies, since container rate indices "
                "(WCI, FBX, SCFI) have no free history; exchange rates. NY Fed Global Supply "
                "Chain Pressure Index (monthly, standard deviations from the average).",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def _name(market: pd.DataFrame, series_id: str) -> str:
    names = market.loc[market["series_id"] == series_id, "name"]
    return names.iloc[0] if len(names) else series_id


def kpi_values(market: pd.DataFrame) -> list[dict]:
    brent = indicators.latest(market, "DCOILBRENTEU")
    spread = indicators.gas_spread(market, "PNGASEUUSDM")
    gscpi = indicators.latest(market, "GSCPI")
    freight_yoy = indicators.change_pct(market, "PCU483111483111", 365)
    brent_change = indicators.change_pct(market, "DCOILBRENTEU", 30)
    return [
        {
            "label": "Brent, USD/bbl",
            "value": charts.number(brent[1] if brent else None),
            "note": f"{charts.signed_pct(brent_change)} vs. 30 days earlier"
            + (f" · {brent[0]:%d %b %Y}" if brent else ""),
        },
        {
            "label": "Gas spread Europe − US, USD/MMBtu",
            "value": charts.number(spread["value"].iloc[-1] if len(spread) else None),
            "note": f"{spread['date'].iloc[-1]:%b %Y}: feedstock edge of US producers"
            if len(spread)
            else "",
        },
        {
            "label": "Supply chain pressure (GSCPI)",
            "value": charts.number(gscpi[1] if gscpi else None, "+.2f"),
            "note": "standard deviations from the average"
            + (f" · {gscpi[0]:%b %Y}" if gscpi else ""),
        },
        {
            "label": "Deep sea freight price index",
            "value": charts.signed_pct(freight_yoy),
            "note": "vs. 12 months earlier (US PPI, proxy)",
        },
    ]


def oil_figure(market: pd.DataFrame, start: pd.Timestamp, key_events: list) -> go.Figure:
    frames = [
        (_name(market, s), indicators.series(market, s)) for s in ["DCOILBRENTEU", "DCOILWTICO"]
    ]
    frames = [(n, f[f["date"] >= start]) for n, f in frames]
    fig = charts.line_chart(frames, "Crude oil", "USD per barrel")
    return charts.add_key_events(fig, key_events, start)


def gas_figure(market: pd.DataFrame, start: pd.Timestamp, key_events: list) -> go.Figure:
    """Monthly averages so the daily US series is comparable with the monthly EU/Japan series."""
    frames = [
        (_name(market, s), indicators.monthly_mean(market, s))
        for s in ["DHHNGSP", "PNGASEUUSDM", "PNGASJPUSDM"]
    ]
    frames = [(n, f[f["date"] >= start]) for n, f in frames]
    fig = charts.line_chart(frames, "Natural gas, monthly average", "USD per MMBtu")
    return charts.add_key_events(fig, key_events, start)


def indexed_figure(market: pd.DataFrame, start: pd.Timestamp, key_events: list) -> go.Figure:
    ids = ["PCU483111483111", "PCU3252113252111", "DEXCHUS", "DTWEXBGS"]
    rebased = indicators.indexed(market, ids, start)
    # Empty series are skipped by `line_chart` without shifting the other colours.
    frames = [(_name(market, s), rebased[rebased["series_id"] == s]) for s in ids]
    fig = charts.line_chart(
        frames, "Freight, resins and currencies (start of period = 100)", "index"
    )
    fig.add_hline(y=100, line={"color": style.GRID, "width": 1})
    return charts.add_key_events(fig, key_events, start)


def gscpi_figure(market: pd.DataFrame, start: pd.Timestamp, key_events: list) -> go.Figure:
    one = indicators.series(market, "GSCPI")
    one = one[one["date"] >= start]
    fig = go.Figure(
        go.Bar(
            x=one["date"],
            y=one["value"],
            marker={"color": [style.ORANGE if v > 0 else style.BLUE for v in one["value"]]},
            name="GSCPI",
            hovertemplate="%{y:+.2f}",
        )
    )
    fig.add_hline(y=0, line={"color": style.INK_SECONDARY, "width": 1})
    fig.update_yaxes(title={"text": "std. dev. from average", "font": {"color": style.MUTED}})
    charts.base_layout(fig, height=340, title="Global Supply Chain Pressure Index (NY Fed)")
    return charts.add_key_events(fig, key_events, start)


def update(data: AppData, period: str) -> tuple:
    market = data.market
    latest = market["date"].max()
    start = charts.period_start(period, latest, market["date"].min())
    events = data.market_config.key_events
    return (
        charts.tiles(kpi_values(market)),
        oil_figure(market, start, events),
        gas_figure(market, start, events),
        indexed_figure(market, start, events),
        gscpi_figure(market, start, events),
    )


def register(app: Dash, state: AppState) -> None:
    if state.data.market is None:
        return

    @app.callback(
        Output("mkt-kpis", "children"),
        Output("mkt-oil", "figure"),
        Output("mkt-gas", "figure"),
        Output("mkt-indexed", "figure"),
        Output("mkt-gscpi", "figure"),
        Input("mkt-period", "value"),
        Input("data-version", "data"),
    )
    def _update(period: str, _version: int) -> tuple:
        return update(state.data, period)
