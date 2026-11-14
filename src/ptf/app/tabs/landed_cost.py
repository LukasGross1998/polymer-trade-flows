"""Tab "Landed cost": what does a tonne cost delivered to Europe from each supplier country?

Price (BACI unit value), sea freight and EU duty, in EUR/t; with the Red Sea open or closed,
a freight factor and prices of the BACI year or indexed to today (spec 007).
"""

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
    route_options = [{"label": "Red Sea open", "value": "open"}]
    if data.distances_closed is not None:
        route_options.append({"label": "Red Sea closed (via the Cape)", "value": "closed"})
    return html.Div(
        [
            html.Div(
                [
                    charts.control("Grade", grade_dropdown("lc-grade", data)),
                    charts.control(
                        "Route",
                        radio("lc-route", route_options, "open"),
                    ),
                    charts.control(
                        "Freight rates (× assumption)",
                        dcc.Slider(
                            id="lc-freight",
                            min=0.5,
                            max=3.0,
                            step=0.25,
                            value=1.0,
                            marks={v: f"{v:g}×" for v in [0.5, 1, 1.5, 2, 2.5, 3]},
                        ),
                    ),
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
                "(latest / average of the BACI year): a proxy, not a quote. Freight: assumption "
                "of the transport model (40 USD/t + 7 USD/t per 1,000 nm, config/model.yaml) "
                "from one port per region. EU duty on price + freight (CIF), rates in "
                "the third-country rate per grade from World Bank WITS (highest tariff line of the "
                "grade), preferential rates in config/sourcing.yaml (TARIC mirror). "
                "Reference line: average price of trade within Europe. The model region Europe "
                "also includes the UK, Turkey, Switzerland, Norway and Ukraine, where EU duties do "
                "not apply (e.g. most imports from Iran go to Turkey); GSP preferences (e.g. "
                "Uzbekistan) are not modelled.",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def compute(
    data: AppData, route: str, freight_factor: float, basis: str, grade: str = ALL_GRADES
) -> LandedView | None:
    sources = data.sources(grade)
    if sources is None or sources.empty or data.distances is None:
        return None
    return landed_view(
        sources,
        data.market,
        data.distances,
        data.distances_closed,
        data.model_config.freight,
        data.sourcing_config,
        red_sea_closed=route == "closed",
        freight_factor=freight_factor,
        indexed_prices=basis == "indexed",
        mfn_pct=mfn_rate(
            data.eu_duty,
            data.import_sources_by_product,
            grade,
            data.sourcing_config.focus_region,
        ),
    )


def kpi_values(view: LandedView) -> list[dict[str, str]]:
    cheapest = view.table.iloc[0]
    gap = None if view.reference_eur_t is None else cheapest["landed_eur_t"] - view.reference_eur_t
    return [
        {
            "label": "Cheapest origin, delivered",
            "value": f"{cheapest['landed_eur_t']:,.0f} EUR/t",
            "note": str(cheapest["exporter_name"]),
        },
        {
            "label": "vs. buying within Europe",
            "value": "n/a" if gap is None else f"{gap:+,.0f} EUR/t",
            "note": "n/a"
            if view.reference_eur_t is None
            else f"European average {view.reference_eur_t:,.0f} EUR/t",
        },
        {
            "label": "Red Sea closure, Middle East",
            "value": "n/a"
            if view.closure_extra_eur_t is None
            else f"{view.closure_extra_eur_t:+,.0f} EUR/t",
            "note": "extra landed cost via the Cape, volume-weighted",
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
    table = view.table.iloc[::-1]  # cheapest on top in a horizontal bar chart
    fig = go.Figure()
    for colour, part in zip(style.SERIES, COMPONENT_LABELS, strict=False):
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
    fig.update_xaxes(
        title={"text": "EUR per tonne, delivered to Europe", "font": {"color": style.MUTED}}
    )
    return charts.base_layout(
        fig, height=440, title="Landed cost by supplier country (10 largest by volume)"
    )


def cost_table(view: LandedView) -> html.Table:
    header = ["Country", "kt", "nm", "Price", "Freight", "Duty %", "Duty", "Landed EUR/t"]
    cell = {"padding": "4px 8px", "fontSize": "13px", "textAlign": "right"}
    rows = [html.Tr([html.Th(h, style={**cell, "color": style.MUTED}) for h in header])]
    for row in view.table.to_dict("records"):
        values = [
            row["exporter_name"],
            f"{row['qty_t'] / 1e3:,.0f}",
            f"{row['distance_nm']:,.0f}",
            f"{row['price_eur_t']:,.0f}",
            f"{row['freight_eur_t']:,.0f}",
            f"{row['duty_pct']:.1f}",
            f"{row['duty_eur_t']:,.0f}",
            f"{row['landed_eur_t']:,.0f}",
        ]
        rows.append(
            html.Tr(
                [html.Td(values[0], style={**cell, "textAlign": "left"})]
                + [html.Td(v, style=cell) for v in values[1:]]
            )
        )
    return html.Table(rows, style={"borderCollapse": "collapse", "width": "100%"})


def update(
    data: AppData, route: str, freight_factor: float, basis: str, grade: str = ALL_GRADES
) -> charts.Outputs:
    view = compute(data, route, freight_factor, basis, grade)
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
        Input("lc-route", "value"),
        Input("lc-freight", "value"),
        Input("lc-basis", "value"),
        Input("lc-grade", "value"),
        Input("data-version", "data"),
    )
    def _update(
        route: str, freight_factor: float, basis: str, grade: str, _version: int
    ) -> charts.Outputs:
        return update(state.data, route, freight_factor, basis, grade)
