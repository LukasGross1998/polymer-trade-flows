"""Tab "Prices & drivers": where is the raw-material price heading, in EUR or USD?

Feedstock (oil, gas) and resin price indices side by side, freight and currencies, and
supply-chain stress. USD-based series can be shown in EUR (spec 006).
"""

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, html

from ptf.app import charts, fmt, theme
from ptf.app.data import AppData, AppState, require
from ptf.markets import indicators
from ptf.markets.config import KeyEvent

# Feedstock and resin series compared on one indexed axis.
DRIVER_SERIES = [
    "DCOILBRENTEU",
    "DHHNGSP",
    "PNGASEUUSDM",
    "PCU3252113252111",
    "PCU325211325211",
]
DRIVER_BASE = pd.Timestamp("2019-01-01")


def layout(data: AppData) -> html.Div:
    if data.market is None:
        return charts.no_data("No market data loaded yet – use Update data.")
    card = {**theme.CARD, "flex": "1", "minWidth": "420px"}
    return html.Div(
        [
            html.Div(
                [
                    charts.control("Period", charts.period_dropdown("mkt-period", "5y")),
                ],
                style=theme.ROW,
            ),
            html.Div(id="mkt-kpis", style=theme.ROW),
            html.Div(
                [
                    html.Div(charts.graph("mkt-drivers"), style={**theme.CARD, "flex": "2"}),
                    html.Div(charts.graph("mkt-resin"), style={**theme.CARD, "flex": "1"}),
                ],
                style=theme.ROW,
            ),
            html.Div(
                [
                    html.Div(id="mkt-dce-quote", style={"fontSize": "13px", "marginBottom": "4px"}),
                    charts.graph("mkt-dce"),
                    theme.method_panel(
                        "Source: Dalian Commodity Exchange, LLDPE main contract (closing price), "
                        "via Sina Finance and the AKShare library – an unofficial source, by "
                        "AKShare's own statement for research only. Price for delivery in China in "
                        "CNY per tonne including VAT, converted with FRED DEXCHUS (and DEXUSEU); "
                        "an indicator of the Asian market, not comparable 1:1 with export or "
                        "European contract prices. Downloaded only where the optional Asian "
                        "price source is installed (see the README).",
                    ),
                ],
                style={**theme.CARD, "marginBottom": "16px"},
            ),
            html.Div(
                [
                    html.Div(charts.graph("mkt-oil"), style=card),
                    html.Div(charts.graph("mkt-gas"), style=card),
                ],
                style=theme.ROW,
            ),
            html.Div(
                [
                    html.Div(charts.graph("mkt-indexed"), style={**card, "flex": "2"}),
                    html.Div(charts.graph("mkt-gscpi"), style={**card, "minWidth": "300px"}),
                ],
                style=theme.ROW,
            ),
            html.Div([html.Div(charts.graph("mkt-fx"), style=card)], style=theme.ROW),
            theme.method_panel(
                "Polymer over crude: Dalian LLDPE minus Brent per tonne, with "
                f"{fmt.number(barrels(data), 2)}"
                " barrels per tonne of crude (UN Energy Statistics Yearbook 2023, Table II); "
                "Brent on the last day up to four days before a Dalian trading day. A wide spread "
                "means polymer prices high relative to crude. WTI, LNG Japan and the CNY and "
                "dollar index series are still downloaded but no longer drawn. "
                "Sources: FRED (St. Louis Fed): Brent, WTI, Henry Hub (daily); natural gas Europe "
                "and LNG Japan (IMF, monthly); US producer price indices for deep sea freight and "
                "thermoplastic resins (BLS, monthly) as proxies, since container rate indices "
                "(WCI, FBX, SCFI) have no free history; exchange rates. NY Fed Global Supply "
                "Chain Pressure Index (monthly, standard deviations from the average). "
                "EUR: converted with the ECB-based USD/EUR rate from FRED (DEXUSEU), same day for "
                "daily prices, monthly average for monthly series; the US price indices are "
                "USD-based and converted the same way.",
            ),
        ]
    )


def _name(market: pd.DataFrame, series_id: str) -> str:
    names = market.loc[market["series_id"] == series_id, "name"]
    return names.iloc[0] if len(names) else series_id


def standard_delta(market: pd.DataFrame, series_id: str) -> str:
    """Change against the standard period (spec 017): 30 days for daily, one month for
    monthly series."""
    one = indicators.series(market, series_id)
    if one.empty:
        return ""
    monthly = (one["date"].diff().dt.days.median() or 0) > 20
    days, period = (28, "previous month") if monthly else (30, "30 days")
    return charts.delta_text(indicators.change_pct(market, series_id, days), period)


def recent(market: pd.DataFrame, series_id: str, days: int = 365) -> pd.DataFrame:
    one = indicators.series(market, series_id)
    return one[one["date"] > one["date"].max() - pd.Timedelta(days=days)] if len(one) else one


def kpi_values(market: pd.DataFrame, currency: str = "USD") -> list[dict[str, Any]]:
    brent = indicators.latest(market, "DCOILBRENTEU")
    spread = indicators.gas_spread(market, "PNGASEUUSDM")
    gscpi = indicators.latest(market, "GSCPI")
    freight = indicators.latest(market, "PCU483111483111")
    values: list[dict[str, Any]] = [
        {
            "label": "Brent crude oil",
            "value": fmt.number(brent[1] if brent else None, 1),
            "unit": f"{currency}/bbl",
            "delta": standard_delta(market, "DCOILBRENTEU"),
            "date": f"{brent[0]:%d %b %Y}" if brent else "",
            "spark": recent(market, "DCOILBRENTEU"),
        },
        {
            "label": "Gas spread Europe − US",
            "value": fmt.number(spread["value"].iloc[-1] if len(spread) else None, 1),
            "unit": f"{currency}/MMBtu",
            "note": "feedstock edge of US producers",
            "date": f"{spread['date'].iloc[-1]:%b %Y}" if len(spread) else "",
        },
        {
            "label": "Supply chain pressure (GSCPI)",
            "value": fmt.number(gscpi[1] if gscpi else None, 2, signed=True),
            "unit": "std. dev.",
            "note": "standard deviations from the long-run average (NY Fed)",
            "date": f"{gscpi[0]:%b %Y}" if gscpi else "",
        },
        {
            "label": "Deep sea freight price index",
            "value": fmt.number(freight[1] if freight else None, 1),
            "unit": "index",
            "delta": standard_delta(market, "PCU483111483111"),
            "note": "US producer price index, a proxy for ocean freight",
            "date": f"{freight[0]:%b %Y}" if freight else "",
        },
    ]
    eu_ppi = indicators.latest(market, "EU_PPI_PLASTICS")
    if eu_ppi is not None:
        values.append(
            {
                "label": "EU producer prices, plastics in primary forms",
                "value": fmt.number(eu_ppi[1], 1),
                "unit": "index 2021 = 100",
                "delta": standard_delta(market, "EU_PPI_PLASTICS"),
                "note": "Eurostat: the European price anchor (an index, not a price)",
                "date": f"{eu_ppi[0]:%b %Y}",
                "spark": recent(market, "EU_PPI_PLASTICS", 3 * 365),
            }
        )
    dce = dce_in_currency(market, currency)
    if not dce.empty:
        last = dce.iloc[-1]
        earlier = dce[dce["date"] <= last["date"] - pd.Timedelta(days=30)]
        change = None if earlier.empty else (last["value"] / earlier.iloc[-1]["value"] - 1) * 100
        values.append(
            {
                "label": "LLDPE Dalian (Asian indicator)",
                "value": fmt.number(last["value"]),
                "unit": f"{currency}/t",
                "delta": charts.delta_text(change, "30 days"),
                "note": "unofficial source",
                "date": f"{last['date']:%d %b %Y}",
                "spark": dce[dce["date"] > last["date"] - pd.Timedelta(days=365)],
            }
        )
    return values


def drivers_figure(
    market: pd.DataFrame,
    currency: str,
    key_events: list[KeyEvent],
    start: pd.Timestamp | None = None,
    barrels_per_tonne: float | None = None,
) -> go.Figure:
    """Polymer over crude (spec 018): Dalian LLDPE minus Brent per tonne, both in `currency`.

    A rising spread means polymer prices rise faster than crude (or fall slower): margin,
    not feedstock. Without a sourced conversion factor or without the Dalian price no spread
    is drawn.
    """
    title = f"Polymer over crude: LLDPE Dalian minus Brent, {currency} per tonne"
    dce = dce_in_currency(market, currency)
    brent = indicators.series(market, "DCOILBRENTEU")
    if barrels_per_tonne is None or dce.empty or brent.empty:
        return empty_figure(title, "No spread: Dalian price or crude conversion factor missing.")
    gap = indicators.spread(dce, indicators.per_tonne(brent, barrels_per_tonne))
    if start is not None:
        gap = gap[gap["date"] >= start]
    fig = go.Figure(
        go.Scatter(
            x=gap["date"],
            y=gap["value"],
            mode="lines",
            fill="tozeroy",
            line={"color": theme.BLUE, "width": 2},
            fillcolor=theme.with_alpha(theme.BLUE, 0.15),
            name="LLDPE − Brent",
            hovertemplate="%{y:,.0f} " + currency + "/t",
        )
    )
    fig.update_yaxes(title={"text": f"{currency} per tonne", "font": {"color": theme.MUTED}})
    charts.base_layout(fig, height=340, title=title)
    if len(gap):
        charts.add_key_events(fig, key_events, gap["date"].min(), gap["date"].max())
    return fig


def resin_figure(market: pd.DataFrame, start: pd.Timestamp) -> go.Figure:
    """The US resin price index on its own (an index, not a price: not subtracted)."""
    one = indicators.series(market, "PCU325211325211")
    one = one[one["date"] >= start]
    return charts.line_chart(
        [("US PPI plastics resins", one)], "US resin price index (BLS, monthly)", "index"
    )


def empty_figure(title: str, message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font={"color": theme.MUTED})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return charts.base_layout(fig, height=200, title=title)


DCE_SERIES = "DCE_LLDPE"
DCE_TITLE = "Asian price indicator: LLDPE futures, Dalian"


def dce_in_currency(market: pd.DataFrame, currency: str) -> pd.DataFrame:
    """The DCE LLDPE price converted from CNY to USD, and to EUR if chosen; empty if missing."""
    cny = indicators.series(market, DCE_SERIES)
    rates = indicators.series(market, "DEXCHUS")
    if cny.empty or rates.empty:
        return cny.iloc[0:0]
    usd = indicators.cny_to_usd(cny, rates)
    if currency == "EUR":
        return indicators.usd_to_eur(usd, indicators.series(market, "DEXUSEU"))
    return usd


def close_note(data: AppData) -> str:
    """'Daily price = close of the trading day, 15:00 Beijing time (08:00 CET in winter).'"""
    dce = data.market_config.dce
    if dce is None or dce.day_close_hour is None:
        return "Daily price = closing price of the trading day."
    hour = int(dce.day_close_hour.value)
    # Beijing is UTC+8; Central Europe UTC+1 in winter, UTC+2 in summer.
    return (
        f"Daily price = closing price of the trading day, {hour}:00 Beijing time "
        f"({hour - 7:02d}:00 CET in winter, {hour - 6:02d}:00 CEST in summer)."
    )


def quote_line(data: AppData, currency: str) -> str:
    """The latest intraday quote, if it belongs to a newer trading day than the last close,
    and in plain words what the daily price is (spec 018)."""
    hours = close_note(data)
    quote = data.dce_quote
    market = data.market
    if quote is None or quote.empty or market is None:
        return hours
    row = quote.iloc[0]
    closes = indicators.series(market, DCE_SERIES)
    if not closes.empty and row["trading_day"] <= closes["date"].max():
        return hours  # the daily close already covers this trading day
    # One price, so convert with the latest rates: CNY -> USD (DEXCHUS = CNY per USD), then
    # USD -> EUR (DEXUSEU = USD per EUR) if EUR is chosen.
    in_currency = ""
    cny_per_usd = indicators.latest(market, "DEXCHUS")
    usd_per_eur = indicators.latest(market, "DEXUSEU")
    if cny_per_usd is not None:
        value = row["last_cny_t"] / cny_per_usd[1]
        if currency == "EUR" and usd_per_eur is not None:
            value = value / usd_per_eur[1]
        if currency == "USD" or usd_per_eur is not None:
            in_currency = f" ≈ {value:,.0f} {currency}/t"
    fetched = pd.Timestamp(row["fetched_at"]).tz_convert("Europe/Berlin")
    return (
        f"Latest quote: {row['last_cny_t']:,.0f} CNY/t{in_currency} (bid {row['bid_cny_t']:,.0f} / "
        f"ask {row['ask_cny_t']:,.0f}), last trade {row['tick_time_beijing']} Beijing time, "
        f"trading day {pd.Timestamp(row['trading_day']):%d %b}; fetched {fetched:%a %d %b %H:%M}. "
        + hours
    )


def dce_figure(market: pd.DataFrame, start: pd.Timestamp, currency: str) -> go.Figure:
    converted = dce_in_currency(market, currency)
    if converted.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="Dalian price not available: the optional Asian price source is not installed "
            "or not downloaded yet (see the README).",
            showarrow=False,
            font={"color": theme.MUTED},
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return charts.base_layout(fig, height=200, title=DCE_TITLE)
    frame = converted[converted["date"] >= start]
    return charts.line_chart(
        [(f"LLDPE Dalian, {currency}/t", frame)],
        f"{DCE_TITLE}, {currency} per tonne (daily close)",
        f"{currency} per tonne",
    )


def oil_figure(
    market: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    key_events: list[KeyEvent],
    currency: str = "USD",
) -> go.Figure:
    brent = indicators.series(market, "DCOILBRENTEU")
    frames = [(_name(market, "DCOILBRENTEU"), brent[brent["date"] >= start])]
    fig = charts.line_chart(frames, "Crude oil: Brent", f"{currency} per barrel")
    return charts.add_key_events(fig, key_events, start, end)


def gas_figure(
    market: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    key_events: list[KeyEvent],
    currency: str = "USD",
) -> go.Figure:
    """Gas spread Europe − US as an area; the two prices hidden until clicked in the legend."""
    gap = indicators.gas_spread(market, "PNGASEUUSDM")
    gap = gap[gap["date"] >= start]
    fig = go.Figure(
        go.Scatter(
            x=gap["date"],
            y=gap["value"],
            mode="lines",
            fill="tozeroy",
            name="Europe − US",
            line={"color": theme.BLUE, "width": 2},
            fillcolor=theme.with_alpha(theme.BLUE, 0.15),
            hovertemplate="%{y:,.1f}",
        )
    )
    for colour, series_id in zip(theme.SERIES[1:3], ["PNGASEUUSDM", "DHHNGSP"], strict=True):
        one = indicators.monthly_mean(market, series_id)
        one = one[one["date"] >= start]
        fig.add_trace(
            go.Scatter(
                x=one["date"],
                y=one["value"],
                mode="lines",
                name=_name(market, series_id),
                line={"color": colour, "width": 1.5},
                visible="legendonly",
            )
        )
    fig.update_yaxes(title={"text": f"{currency} per MMBtu", "font": {"color": theme.MUTED}})
    charts.base_layout(fig, height=340, title="Natural gas: spread Europe − US (monthly)")
    return charts.add_key_events(fig, key_events, start, end)


def indexed_figure(
    market: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, key_events: list[KeyEvent]
) -> go.Figure:
    """Ocean freight on its own (spec 018): the US PPI for deep sea freight."""
    one = indicators.series(market, "PCU483111483111")
    one = one[one["date"] >= start]
    fig = charts.line_chart(
        [(_name(market, "PCU483111483111"), one)],
        "Ocean freight: US producer price index, deep sea freight (monthly)",
        "index",
    )
    return charts.add_key_events(fig, key_events, start, end)


def fx_figure(market: pd.DataFrame, start: pd.Timestamp) -> go.Figure:
    """EUR/USD only (USD per EUR): up = stronger euro, dollar imports cheaper in EUR."""
    one = indicators.series(market, "DEXUSEU")
    one = one[one["date"] >= start]
    return charts.line_chart(
        [("US dollars per euro", one)], "Exchange rate: US dollars per euro", "USD per EUR"
    )


def gscpi_figure(
    market: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, key_events: list[KeyEvent]
) -> go.Figure:
    one = indicators.series(market, "GSCPI")
    one = one[one["date"] >= start]
    fig = go.Figure(
        go.Bar(
            x=one["date"],
            y=one["value"],
            # Diverging colours: red = more pressure than average, blue = less.
            marker={"color": [theme.DIVERGING_LOW if v > 0 else theme.BLUE for v in one["value"]]},
            name="GSCPI",
            hovertemplate="%{y:+.2f}",
        )
    )
    fig.add_hline(y=0, line={"color": theme.INK_SECONDARY, "width": 1})
    fig.update_yaxes(title={"text": "std. dev. from average", "font": {"color": theme.MUTED}})
    charts.base_layout(fig, height=340, title="Context: supply chain pressure (GSCPI, NY Fed)")
    return charts.add_key_events(fig, key_events, start, end)


def update(data: AppData, period: str, currency: str = "EUR") -> charts.Outputs:
    raw = require(data.market, "market_series")
    market = indicators.in_currency(raw, currency)
    latest = market["date"].max()
    start = charts.period_start(period, latest, market["date"].min())
    events = data.market_config.key_events
    return (
        charts.tiles(kpi_values(market, currency)),
        drivers_figure(market, currency, events, start, barrels(data)),
        resin_figure(raw, start),
        dce_figure(market, start, currency),
        quote_line(data, currency),
        oil_figure(market, start, latest, events, currency),
        gas_figure(market, start, latest, events, currency),
        indexed_figure(market, start, latest, events),
        gscpi_figure(market, start, latest, events),
        fx_figure(raw, start),
    )


def barrels(data: AppData) -> float | None:
    factor = data.market_config.crude_barrels_per_tonne
    return None if factor is None else factor.value


def register(app: Dash, state: AppState) -> None:
    if state.data.market is None:
        return

    @app.callback(
        Output("mkt-kpis", "children"),
        Output("mkt-drivers", "figure"),
        Output("mkt-resin", "figure"),
        Output("mkt-dce", "figure"),
        Output("mkt-dce-quote", "children"),
        Output("mkt-oil", "figure"),
        Output("mkt-gas", "figure"),
        Output("mkt-indexed", "figure"),
        Output("mkt-gscpi", "figure"),
        Output("mkt-fx", "figure"),
        Input("mkt-period", "value"),
        Input("currency", "value"),
        Input("data-version", "data"),
    )
    def _update(period: str, currency: str, _version: int) -> charts.Outputs:
        return update(state.data, period, currency)
