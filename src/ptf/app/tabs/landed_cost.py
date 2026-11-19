"""Tab "Landed cost": what does a tonne cost delivered to Europe from each supplier country?

Price (BACI unit value), sea freight and EU duty, in EUR/t; with the Red Sea open or closed
and prices of the BACI year or indexed to today (spec 007). Spec 015: freight is shown only
with a sourced rate; until then the tab shows price + duty and says so. Spec 016: price
ranges by grade, confidence, sourceable origins, capital tied up in transit and the buyer's
own cost quotes.
"""

from collections.abc import Hashable, Mapping
from typing import Any

import pandas as pd
from dash import Dash, Input, Output, dcc, html

from ptf.app import charts, fmt, theme
from ptf.app.data import AppData, AppState
from ptf.insights import landed_cost as landed_cost_logic
from ptf.insights.view import ALL_GRADES, CostQuotes, LandedView, landed_view, mfn_rate
from ptf.markets import indicators

QUOTE = "your quote"


def number_input(component_id: str, placeholder: str) -> dcc.Input:
    """A field for the buyer's own quote; empty means "not included"."""
    return dcc.Input(
        id=component_id,
        type="number",
        min=0,
        placeholder=placeholder,
        debounce=True,
        style={"width": "120px"},
    )


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
        return charts.no_data("No trade data or sea routes loaded yet.")
    return html.Div(
        [
            theme.method_panel(
                "Price: BACI unit value of each country's exports to Europe (value / tonnes, FOB), "
                "an annual average over all polyethylene grades – part of the differences is the "
                "product mix. 'Indexed to today' scales it with the US PPI for plastics resins "
                "(FRED, latest / average of the BACI year): a proxy, not a quote. Sea freight: "
                "n/a – no free source gives a rate per tonne for these routes (spec 015); "
                "'landed' is therefore price + duty, excluding freight. EU duty: third-country "
                "rate per grade from World Bank WITS (highest tariff line of the grade), "
                "preferences from EU TARIC with their validity (read 14 Nov 2026), on the price "
                "while freight is unknown. Price: average over all grades; in brackets the "
                "lowest to highest grade price (HS6) among the main grades, those with at least "
                f"{data.sourcing_config.price_range.min_grade_share:g} % of the country's "
                "tonnes (the average can lie outside when small special grades are "
                "expensive); confidence from volume, product-mix effect and data age (hover the "
                "level). Capital in transit: price × euro 3-month interbank rate (OECD via "
                "FRED) × ship transit days / 365. Insurance, port handling and on-carriage only "
                "if you enter your quote. Not sourceable (greyed out): EU import control in "
                "TARIC. Reference line: average price of trade within Europe. The model region "
                "Europe also includes the UK, Turkey, Switzerland, Norway and Ukraine, where EU "
                "duties do not apply.",
            ),
            html.Div(
                [
                    charts.control(
                        "Price basis",
                        radio(
                            "lc-basis",
                            [
                                *(
                                    [{"label": "Comext, last 12 months (CIF)", "value": COMEXT}]
                                    if has_comext(data)
                                    else []
                                ),
                                {"label": "BACI unit value", "value": "baci"},
                                {"label": "BACI indexed to today", "value": "indexed"},
                            ],
                            default_basis(data),
                        ),
                    ),
                    charts.control(
                        "Insurance, % of price", number_input("lc-insurance", "your quote")
                    ),
                    charts.control(
                        "Port handling, EUR/t", number_input("lc-handling", "your quote")
                    ),
                    charts.control(
                        "On-carriage, EUR/t", number_input("lc-oncarriage", "your quote")
                    ),
                ],
                style=theme.ROW,
            ),
            html.Div(id="lc-kpis", style=theme.ROW),
            html.Div(id="lc-table", style={**theme.CARD, "marginBottom": "16px"}),
        ]
    )


COMEXT = "comext"


def has_comext(data: AppData) -> bool:
    return data.eu_imports is not None and not data.eu_imports.empty


def default_basis(data: AppData) -> str:
    """Comext (monthly, CIF) when loaded, else the BACI annual unit value (spec 019)."""
    return COMEXT if has_comext(data) else "baci"


def grade_rows(data: AppData, grade: str) -> pd.DataFrame | None:
    """BACI imports per grade, filtered to one grade if chosen (price ranges, spec 016)."""
    by_product = data.import_sources_by_product
    if by_product is None or grade == ALL_GRADES:
        return by_product
    return by_product[by_product["hs6"] == grade]


def compute(
    data: AppData,
    scenario: str,
    basis: str,
    grade: str = ALL_GRADES,
    quotes: CostQuotes | None = None,
) -> LandedView | None:
    sources = data.sources(grade)
    tables = data.route_tables
    if sources is None or sources.empty or tables is None:
        return None
    by_product = grade_rows(data, grade)
    extra: dict[str, Any] = {}
    if basis == COMEXT and has_comext(data):
        assert data.eu_imports is not None
        monthly = data.eu_imports
        if grade != ALL_GRADES:
            monthly = monthly[monthly["hs6"] == grade]
        fx = indicators.latest(data.market, "DEXUSEU") if data.market is not None else None
        comext_sources, comext_by_product, label = landed_cost_logic.comext_sources(
            monthly, data.sourcing_config.focus_region, fx[1] if fx else 1.0
        )
        extra = {
            "reference_sources": sources,
            "reference_by_product": by_product,
            "cif": True,
            "basis_label": label,
        }
        sources, by_product = comext_sources, comext_by_product
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
        by_product=by_product,
        quotes=quotes,
        **extra,
    )


FREIGHT_NA = "n/a – no sourced freight rate"
CIF_NOTE = "incl. (CIF)"


def delivery(view: LandedView) -> str:
    """How far the cost reaches: the EU border (Comext CIF), delivered, or excl. freight."""
    if view.cif:
        return "CIF EU border + duty"
    return "delivered" if view.freight_known else "excl. freight"


def kpi_values(view: LandedView) -> list[dict[str, str]]:
    usable = view.table[view.table["sourceable"].fillna(True)]
    cheapest = usable.iloc[0] if not usable.empty else view.table.iloc[0]
    delivered = delivery(view)
    unit = f"{view.currency}/t"
    as_of = view.basis_label + (", monthly, CIF" if view.cif else ", annual unit values")
    return [
        {
            "label": f"Lowest cost sourceable origin, {delivered}",
            "value": fmt.number(cheapest["total_eur_t"]),
            "unit": unit,
            "note": f"{cheapest['exporter_name']}, confidence {cheapest['confidence']}",
            "date": as_of,
        },
        {
            "label": "vs. buying within Europe, same grades",
            "value": fmt.span(
                cheapest["vs_europe_low_eur_t"], cheapest["vs_europe_high_eur_t"], signed=True
            ),
            "unit": unit,
            "note": f"{cheapest['exporter_name']}: price + duty per grade minus the price within "
            "Europe (BACI)" + ("" if view.freight_known else ", excl. freight"),
            "date": as_of,
        },
        {
            "label": "Scenario vs. all routes open, Middle East",
            "value": fmt.number(view.closure_extra_eur_t, signed=True),
            "unit": unit if view.closure_extra_eur_t is not None else "",
            "note": "extra landed cost via the Cape, volume-weighted"
            if view.freight_known
            else FREIGHT_NA,
        },
    ]


def basis_line(view: LandedView) -> str:
    """The basis of all figures (spec 017: a footnote, not a tile)."""
    interest = (
        "n/a"
        if view.interest is None
        else f"{fmt.number(view.interest[1], 2)} % ({view.interest[0]:%b %Y})"
    )
    index = f" × {view.price_scale:.2f} (resin index)" if view.price_scale != 1 else ""
    return (
        f"Basis: {fmt.number(view.usd_per_eur, 3)} USD/EUR (FRED); prices {view.basis_label}"
        f"{index}; {view.duty_source}; euro 3-month rate {interest}."
    )


# Cost components of the inline bars, in the categorical order of the theme (spec 018).
SEGMENTS = [
    ("price_eur_t", "Price (FOB)"),
    ("duty_eur_t", "EU duty"),
    ("freight_eur_t", "Sea freight"),
    ("capital_eur_t", "Capital in transit"),
    ("quotes_eur_t", "Your quotes"),
]
SEGMENT_COLOURS = dict(zip([key for key, _ in SEGMENTS], theme.SERIES, strict=True))


def segments(row: Mapping[Any, Any]) -> list[tuple[str, float]]:
    """(component, EUR/t) of one row, components without a value left out."""
    quotes = [row.get(q) for q in ("insurance_eur_t", "handling_eur_t", "oncarriage_eur_t")]
    values = {**row, "quotes_eur_t": sum(q for q in quotes if q is not None and not pd.isna(q))}
    out = []
    for key, _ in SEGMENTS:
        value = values.get(key)
        if value is not None and not pd.isna(value) and value > 0:
            out.append((key, float(value)))
    return out


def inline_bar(
    row: Mapping[Any, Any], scale: float, reference: float | None, faded: bool
) -> html.Div:
    """A stacked bar of the cost components inside a table cell; widths in % of `scale`,
    the "buy in Europe" reference as a thin line."""
    parts = [
        html.Div(
            title=f"{dict(SEGMENTS)[key]}: {fmt.number(value)}",
            style={
                "width": f"{value / scale * 100:.2f}%",
                "backgroundColor": SEGMENT_COLOURS[key],
                "height": "100%",
                "marginRight": "1px",
                "opacity": "0.35" if faded else "1",
            },
        )
        for key, value in segments(row)
    ]
    if reference is not None:
        parts.append(
            html.Div(
                title=f"Buy in Europe: {fmt.number(reference)}",
                style={
                    "position": "absolute",
                    "left": f"{reference / scale * 100:.2f}%",
                    "top": "-2px",
                    "bottom": "-2px",
                    "borderLeft": f"2px dashed {theme.INK_SECONDARY}",
                },
            )
        )
    return html.Div(
        parts,
        style={"display": "flex", "position": "relative", "height": "14px", "minWidth": "180px"},
    )


def legend() -> html.Div:
    items = [
        html.Span(
            [
                html.Span(
                    style={
                        "display": "inline-block",
                        "width": "10px",
                        "height": "10px",
                        "backgroundColor": SEGMENT_COLOURS[key],
                        "marginRight": "4px",
                    }
                ),
                label,
            ],
            style={"marginRight": "14px"},
        )
        for key, label in SEGMENTS
    ]
    items.append(html.Span("┆ buy in Europe (average within Europe)"))
    return html.Div(
        items, style={"fontSize": "12px", "color": theme.INK_SECONDARY, "margin": "4px 0 8px"}
    )


def route_status(row: dict[Hashable, Any]) -> str:
    """Route status in the scenario (spec 014)."""
    if row.get("at_risk"):
        return "⚠ availability uncertain"
    if row.get("delayed"):
        return "detour"
    if row.get("reduced"):
        return "reduced traffic"
    return "open"


def cost_table(view: LandedView) -> html.Div:
    header = [
        "Country",
        f"Cost per tonne ({view.currency})",
        "Confidence",
        "1,000 t",
        "Price all grades (main grades)",
        "Freight",
        "Duty",
        "Capital",
        "Your quotes",
        f"Total {view.currency}/t",
        "Route",
    ]
    cell = {"padding": "4px 8px", "fontSize": "13px", "textAlign": "right"}
    rows = [html.Tr([html.Th(h, style={**cell, "color": theme.MUTED}) for h in header])]
    quotes = ["insurance_eur_t", "handling_eur_t", "oncarriage_eur_t"]
    reference = view.reference_eur_t
    scale = max([*view.table["total_eur_t"].tolist(), reference or 0.0]) * 1.05
    for row in view.table.to_dict("records"):
        usable = bool(row.get("sourceable", True))
        entered = [row[q] for q in quotes if not pd.isna(row[q])]
        name = row["exporter_name"] + ("" if usable else " (not sourceable)")
        name += " · minor" if row.get("minor") else ""
        values = [
            str(row["confidence"]),
            f"{row['qty_t'] / 1e3:,.0f}",
            f"{row['price_eur_t']:,.0f} "
            f"({fmt.span(row['price_low_eur_t'], row['price_high_eur_t'])})",
            CIF_NOTE
            if view.cif
            else ("n/a" if pd.isna(row["freight_eur_t"]) else f"{row['freight_eur_t']:,.0f}"),
            f"{row['duty_eur_t']:,.0f} ({row['duty_pct']:.1f} %)",
            "n/a" if pd.isna(row["capital_eur_t"]) else f"{row['capital_eur_t']:,.1f}",
            f"{sum(entered):,.0f}" if entered else "–",
            f"{row['total_eur_t']:,.0f}",
            route_status(row),
        ]
        colour = theme.INK if usable else theme.MUTED
        rows.append(
            html.Tr(
                [
                    html.Td(
                        name,
                        title=row.get("sourceable_reason") or "",
                        style={**cell, "textAlign": "left", "color": colour},
                    ),
                    html.Td(
                        inline_bar(row, scale, reference, not usable),
                        style={**cell, "width": "30%"},
                    ),
                    html.Td(
                        values[0],
                        title=str(row["confidence_reason"]),
                        style={**cell, "color": colour},
                    ),
                ]
                + [html.Td(v, style={**cell, "color": colour}) for v in values[1:]]
            )
        )
    table = html.Table(rows, style={"borderCollapse": "collapse", "width": "100%"})
    missing = "Not included: " + ", ".join(view.not_included) if view.not_included else ""
    title = f"Landed cost by supplier country, {view.currency} per tonne" + (f" ({delivery(view)})")
    return html.Div(
        [
            html.Div(title, style=theme.CARD_TITLE),
            legend(),
            table,
            html.Div(missing, style=theme.SMALL_NOTE),
            html.Div(basis_line(view), style=theme.SMALL_NOTE),
        ]
    )


def update(
    data: AppData,
    scenario: str,
    basis: str,
    grade: str = ALL_GRADES,
    quotes: CostQuotes | None = None,
    currency: str = "EUR",
) -> charts.Outputs:
    view = compute(data, scenario, basis, grade, quotes)
    if view is None or view.table.empty:
        return [], charts.no_data("No suppliers with a sea route.")
    view = view.in_currency(currency)
    return charts.tiles(kpi_values(view)), cost_table(view)


def register(app: Dash, state: AppState) -> None:
    if state.data.import_sources is None or state.data.distances is None:
        return

    @app.callback(
        Output("lc-kpis", "children"),
        Output("lc-table", "children"),
        Input("scenario", "value"),
        Input("lc-basis", "value"),
        Input("grade", "value"),
        Input("lc-insurance", "value"),
        Input("lc-handling", "value"),
        Input("lc-oncarriage", "value"),
        Input("currency", "value"),
        Input("data-version", "data"),
    )
    def _update(
        scenario: str,
        basis: str,
        grade: str,
        insurance: float | None,
        handling: float | None,
        oncarriage: float | None,
        currency: str,
        _version: int,
    ) -> charts.Outputs:
        quotes = CostQuotes(insurance, handling, oncarriage)
        return update(state.data, scenario, basis, grade, quotes, currency)
