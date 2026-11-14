"""Tab "Landed cost": what does a tonne cost delivered to Europe from each supplier country?

Price (BACI unit value), sea freight and EU duty, in EUR/t; with the Red Sea open or closed
and prices of the BACI year or indexed to today (spec 007). Spec 015: freight is shown only
with a sourced rate; until then the tab shows price + duty and says so.
"""

from collections.abc import Hashable
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.app.tabs.sourcing import grade_dropdown
from ptf.insights.view import ALL_GRADES, LandedView, landed_view, mfn_rate

COMPONENT_LABELS = {"price": "Price (FOB)", "freight": "Sea freight", "duty": "EU duty"}


def radio(component_id: str, options: list[dict[str, str]], value: str) -> dcc.RadioItems:
    return dcc.RadioItems(
        id=component_id,
        options=options,
        value=value,
        inline=True,
        inputStyle={"marginRight": "4px", "marginLeft": "8px"},
    )


def layout(data: AppData) -> html.Div:
    if data.import_sources is None or data.distances is None:
        return charts.no_data(
            "No landed-cost data yet: run `uv run ptf clean` (trade marts) and "
            "`uv run ptf ingest` (sea routes)."
        )
    return html.Div(
        [
            html.Div(
                [
                    charts.control("Grade", grade_dropdown("lc-grade", data)),
                    charts.control(
                        "Price basis",
                        radio(
                            "lc-basis",
                            [
                                {"label": "BACI unit value", "value": "baci"},
                                {"label": "Indexed to today", "value": "indexed"},
                            ],
                            "baci",
                        ),
                    ),
                ],
                style=style.ROW,
            ),
            html.Div(id="lc-kpis", style=style.ROW),
            html.Div(charts.graph("lc-bars"), style={**style.CARD, "marginBottom": "16px"}),
            html.Div(id="lc-table", style={**style.CARD, "marginBottom": "16px"}),
            html.Div(
                "Price: BACI unit value of each country's exports to Europe (value / tonnes, FOB), "
                "an annual average over all polyethylene grades – part of the differences is the "
                "product mix. 'Indexed to today' scales it with the US PPI for plastics resins "
                "(FRED, latest / average of the BACI year): a proxy, not a quote. Sea freight: "
                "n/a – no free source gives a rate per tonne for these routes (spec 015); "
                "'landed' is therefore price + duty, excluding freight. EU duty: third-country "
                "rate per grade from World Bank WITS (highest tariff line of the grade), "
                "preferences from EU TARIC with their validity (read 14 Nov 2026), on the price "
                "while freight is unknown. Reference line: average price of trade within "
                "Europe. The model region Europe also includes the UK, Turkey, Switzerland, "
                "Norway and Ukraine, where EU duties do not apply.",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def compute(data: AppData, scenario: str, basis: str, grade: str = ALL_GRADES) -> LandedView | None:
    sources = data.sources(grade)
    tables = data.route_tables
    if sources is None or sources.empty or tables is None:
        return None
    return landed_view(
        sources,
        data.market,
        tables,
        data.chokepoints,
        data.model_config.freight,
        data.sourcing_config,
        data.scenario(scenario),
        indexed_prices=basis == "indexed",
        mfn_pct=mfn_rate(
            data.eu_duty,
            data.import_sources_by_product,
            grade,
            data.sourcing_config.focus_region,
        ),
    )


FREIGHT_NA = "n/a – no sourced freight rate"


def kpi_values(view: LandedView) -> list[dict[str, str]]:
    cheapest = view.table.iloc[0]
    gap = None if view.reference_eur_t is None else cheapest["landed_eur_t"] - view.reference_eur_t
    delivered = "delivered" if view.freight_known else "price + duty, excl. freight"
    return [
        {
            "label": f"Lowest cost origin, {delivered}",
            "value": f"{cheapest['landed_eur_t']:,.0f} EUR/t",
            "note": str(cheapest["exporter_name"]),
        },
        {
            "label": "vs. buying within Europe"
            + ("" if view.freight_known else " (excl. freight)"),
            "value": "n/a" if gap is None else f"{gap:+,.0f} EUR/t",
            "note": "n/a"
            if view.reference_eur_t is None
            else f"European average {view.reference_eur_t:,.0f} EUR/t",
        },
        {
            "label": "Scenario vs. all routes open, Middle East",
            "value": "n/a"
            if view.closure_extra_eur_t is None
            else f"{view.closure_extra_eur_t:+,.0f} EUR/t",
            "note": "extra landed cost via the Cape, volume-weighted"
            if view.freight_known
            else FREIGHT_NA,
        },
        {
            "label": "Basis",
            "value": f"{view.usd_per_eur:.3f} USD/EUR",
            "note": f"prices {view.year}"
            + (f" × {view.price_scale:.2f} (index)" if view.price_scale != 1 else "")
            + f"; {view.duty_source}",
        },
    ]


def bars_figure(view: LandedView) -> go.Figure:
    table = view.table.iloc[::-1].copy()  # cheapest on top in a horizontal bar chart
    table["exporter_name"] = [
        f"{name} ⚠" if risk else name
        for name, risk in zip(table["exporter_name"], table["at_risk"], strict=True)
    ]
    fig = go.Figure()
    for colour, part in zip(style.SERIES, COMPONENT_LABELS, strict=False):
        if table[f"{part}_eur_t"].isna().all():
            continue  # freight without a sourced rate
        fig.add_trace(
            go.Bar(
                y=table["exporter_name"],
                x=table[f"{part}_eur_t"],
                name=COMPONENT_LABELS[part],
                orientation="h",
                marker={"color": colour},
                hovertemplate="%{y}: %{x:,.0f} EUR/t<extra>" + COMPONENT_LABELS[part] + "</extra>",
            )
        )
    if view.reference_eur_t is not None:
        fig.add_vline(
            x=view.reference_eur_t,
            line={"color": style.INK_SECONDARY, "width": 1.5, "dash": "dash"},
            annotation_text="buy in Europe",
            annotation_position="top",
        )
    fig.update_layout(barmode="stack", hovermode="closest", legend={"traceorder": "normal"})
    axis = (
        "EUR per tonne, delivered to Europe"
        if view.freight_known
        else "EUR per tonne, excl. freight"
    )
    fig.update_xaxes(title={"text": axis, "font": {"color": style.MUTED}})
    title = "Landed cost by supplier country (10 largest by volume)"
    if not view.freight_known:
        title = "Price + EU duty by supplier country, excl. freight (10 largest by volume)"
    return charts.base_layout(fig, height=440, title=title)


def route_status(row: dict[Hashable, Any]) -> str:
    """Route status in the scenario (spec 014)."""
    if row.get("at_risk"):
        return "⚠ availability uncertain"
    if row.get("delayed"):
        return "detour"
    if row.get("reduced"):
        return "reduced traffic"
    return "open"


def cost_table(view: LandedView) -> html.Table:
    header = [
        "Country",
        "kt",
        "nm",
        "Price",
        "Freight",
        "Duty %",
        "Duty",
        "Landed EUR/t",
        "Route",
    ]
    cell = {"padding": "4px 8px", "fontSize": "13px", "textAlign": "right"}
    rows = [html.Tr([html.Th(h, style={**cell, "color": style.MUTED}) for h in header])]
    for row in view.table.to_dict("records"):
        values = [
            row["exporter_name"],
            f"{row['qty_t'] / 1e3:,.0f}",
            f"{row['distance_nm']:,.0f}",
            f"{row['price_eur_t']:,.0f}",
            "n/a" if pd.isna(row["freight_eur_t"]) else f"{row['freight_eur_t']:,.0f}",
            f"{row['duty_pct']:.1f}",
            f"{row['duty_eur_t']:,.0f}",
            f"{row['landed_eur_t']:,.0f}",
            route_status(row),
        ]
        rows.append(
            html.Tr(
                [html.Td(values[0], style={**cell, "textAlign": "left"})]
                + [html.Td(v, style=cell) for v in values[1:]]
            )
        )
    return html.Table(rows, style={"borderCollapse": "collapse", "width": "100%"})


def update(data: AppData, scenario: str, basis: str, grade: str = ALL_GRADES) -> charts.Outputs:
    view = compute(data, scenario, basis, grade)
    if view is None or view.table.empty:
        return [], go.Figure(), charts.no_data("No suppliers with a sea route.")
    return charts.tiles(kpi_values(view)), bars_figure(view), cost_table(view)


def register(app: Dash, state: AppState) -> None:
    if state.data.import_sources is None or state.data.distances is None:
        return

    @app.callback(
        Output("lc-kpis", "children"),
        Output("lc-bars", "figure"),
        Output("lc-table", "children"),
        Input("scenario", "value"),
        Input("lc-basis", "value"),
        Input("lc-grade", "value"),
        Input("data-version", "data"),
    )
    def _update(scenario: str, basis: str, grade: str, _version: int) -> charts.Outputs:
        return update(state.data, scenario, basis, grade)
