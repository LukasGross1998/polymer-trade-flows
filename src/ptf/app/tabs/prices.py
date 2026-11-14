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
            html.Div(charts.graph("mkt-drivers"), style={**theme.CARD, "marginBottom": "16px"}),
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
                    html.Div(charts.graph("mkt-indexed"), style=card),
                    html.Div(charts.graph("mkt-gscpi"), style=card),
                ],
                style=theme.ROW,
            ),
            theme.method_panel(
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
) -> go.Figure:
    """Feedstock and resin prices, monthly averages, start of the tab's period = 100
    (spec 017: one period for all charts of the tab; default January 2019).

    If resin indices rise more than feedstock, producers' margins widen (and the other way
    round): the buyer sees whether a price increase is "the market" or margin.
    """
    base = max(start, DRIVER_BASE) if start is not None else DRIVER_BASE
    base = pd.Timestamp(base.year, base.month, 1)
    monthly = indicators.monthly_table(market, DRIVER_SERIES)
    rebased = indicators.indexed(monthly, DRIVER_SERIES, base)
    frames = [(_name(market, s), rebased[rebased["series_id"] == s]) for s in DRIVER_SERIES]
    fig = charts.line_chart(
        frames, f"Feedstock vs. resin prices in {currency} ({base:%B %Y} = 100)", "index"
    )
    fig.add_hline(y=100, line={"color": theme.GRID, "width": 1})
    # Log scale: European gas rose tenfold in 2022 and would flatten every other line;
    # on a log axis equal distances mean equal percentage changes.
    fig.update_yaxes(
        type="log", tickvals=[25, 50, 100, 200, 400, 800], title_text="index, log scale"
    )
    end = monthly["date"].max() if len(monthly) else base
    return charts.add_key_events(fig, key_events, base, end)


DCE_SERIES = "DCE_LLDPE"


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


def quote_line(data: AppData, currency: str) -> str:
    """The latest intraday quote, if it belongs to a newer trading day than the last close.

    Dalian trades (winter, CET) 02:00-04:30, 06:30-08:00 and 14:00-16:00 (night session in
    Beijing), so a quote from a download during those hours is fresher than the daily close.
    """
    hours = "Dalian trading hours (CET, winter): 02:00–04:30, 06:30–08:00, 14:00–16:00."
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
        return charts.base_layout(fig, height=200, title="LLDPE futures, Dalian")
    frame = converted[converted["date"] >= start]
    return charts.line_chart(
        [(f"LLDPE Dalian, {currency}/t", frame)],
        f"LLDPE futures, Dalian main contract, in {currency} per tonne (daily)",
        f"{currency} per tonne",
    )


def oil_figure(
    market: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    key_events: list[KeyEvent],
    currency: str = "USD",
) -> go.Figure:
    frames = [
        (_name(market, s), indicators.series(market, s)) for s in ["DCOILBRENTEU", "DCOILWTICO"]
    ]
    frames = [(n, f[f["date"] >= start]) for n, f in frames]
    fig = charts.line_chart(frames, "Crude oil", f"{currency} per barrel")
    return charts.add_key_events(fig, key_events, start, end)


def gas_figure(
    market: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    key_events: list[KeyEvent],
    currency: str = "USD",
) -> go.Figure:
    """Monthly averages so the daily US series is comparable with the monthly EU/Japan series."""
    frames = [
        (_name(market, s), indicators.monthly_mean(market, s))
        for s in ["DHHNGSP", "PNGASEUUSDM", "PNGASJPUSDM"]
    ]
    frames = [(n, f[f["date"] >= start]) for n, f in frames]
    fig = charts.line_chart(frames, "Natural gas, monthly average", f"{currency} per MMBtu")
    return charts.add_key_events(fig, key_events, start, end)


def indexed_figure(
    market: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, key_events: list[KeyEvent]
) -> go.Figure:
    ids = ["PCU483111483111", "PCU3252113252111", "DEXUSEU", "DEXCHUS", "DTWEXBGS"]
    rebased = indicators.indexed(market, ids, start)
    # Empty series are skipped by `line_chart` without shifting the other colours.
    frames = [(_name(market, s), rebased[rebased["series_id"] == s]) for s in ids]
    fig = charts.line_chart(
        frames, "Freight, resins and currencies (start of period = 100)", "index"
    )
    fig.add_hline(y=100, line={"color": theme.GRID, "width": 1})
    return charts.add_key_events(fig, key_events, start, end)


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
    charts.base_layout(fig, height=340, title="Global Supply Chain Pressure Index (NY Fed)")
    return charts.add_key_events(fig, key_events, start, end)


def update(data: AppData, period: str, currency: str = "EUR") -> charts.Outputs:
    raw = require(data.market, "market_series")
    market = indicators.in_currency(raw, currency)
    latest = market["date"].max()
    start = charts.period_start(period, latest, market["date"].min())
    events = data.market_config.key_events
    return (
        charts.tiles(kpi_values(market, currency)),
        drivers_figure(market, currency, events, start),
        dce_figure(market, start, currency),
        quote_line(data, currency),
        oil_figure(market, start, latest, events, currency),
        gas_figure(market, start, latest, events, currency),
        indexed_figure(market, start, latest, events),
        gscpi_figure(market, start, latest, events),
    )


def register(app: Dash, state: AppState) -> None:
    if state.data.market is None:
        return

    @app.callback(
        Output("mkt-kpis", "children"),
        Output("mkt-drivers", "figure"),
        Output("mkt-dce", "figure"),
        Output("mkt-dce-quote", "children"),
        Output("mkt-oil", "figure"),
        Output("mkt-gas", "figure"),
        Output("mkt-indexed", "figure"),
        Output("mkt-gscpi", "figure"),
        Input("mkt-period", "value"),
        Input("currency", "value"),
        Input("data-version", "data"),
    )
    def _update(period: str, currency: str, _version: int) -> charts.Outputs:
        return update(state.data, period, currency)
