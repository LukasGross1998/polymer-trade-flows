"""Tab "World trade by class": where polyethylene sits in world trade (spec 008).

Commodity classes by tonnes and by value, a drill-down from all goods to the PE grades, and
the development of the classes since 2019. Source: the whole CEPII BACI file (all modes).
"""

import plotly.graph_objects as go
from dash import Dash, Input, Output, html

from ptf.app import charts, style
from ptf.app.data import AppData, AppState
from ptf.trade import classes

BASE_YEAR = 2019


def layout(data: AppData) -> html.Div:
    if data.trade_by_class is None or data.class_tree is None:
        return charts.no_data("No class data yet: run `uv run ptf clean`.")
    year = int(data.trade_by_class["year"].max())
    card = {**style.CARD, "flex": "1", "minWidth": "420px"}
    return html.Div(
        [
            html.Div(id="cls-kpis", style=style.ROW),
            html.Div(
                [
                    html.Div(charts.graph("cls-shares"), style=card),
                    html.Div(charts.graph("cls-treemap"), style=card),
                ],
                style=style.ROW,
            ),
            html.Div(charts.graph("cls-index"), style={**style.CARD, "marginBottom": "16px"}),
            html.Div(
                f"World trade of all goods, CEPII BACI {year} (latest year), all transport modes: "
                "BACI does not tell sea from land, rail, pipeline or air, so these are shares of "
                "world trade, not of seaborne trade (most bulk tonnage moves by sea, but e.g. "
                "pipeline gas and European road freight are included). Classes by HS chapter: "
                "27 mineral fuels, 26 ores, 10 and 12 cereals and oilseeds, 29 organic chemicals, "
                "3901-3914 plastics in primary forms (3901 polyethylene by grade); "
                "dbt/seeds/commodity_classes.csv. Flows without a quantity count with 0 t.",
                style=style.SMALL_NOTE,
            ),
        ]
    )


def kpi_values(data: AppData, year: int) -> list[dict[str, str]]:
    assert data.trade_by_class is not None and data.class_tree is not None
    top = classes.top_level(data.trade_by_class, data.class_tree, year).set_index("class")
    nodes = classes.drilldown(data.trade_by_class, data.class_tree, year).set_index("class")

    def node(name: str, column: str) -> float | None:
        value = nodes[column].to_dict().get(name)
        return None if value is None else float(value)

    def top_share(name: str, column: str) -> float | None:
        value = top[column].to_dict().get(name)
        return None if value is None else float(value) * 100

    world_t, world_usd = node(classes.ROOT, "qty_t") or 0.0, node(classes.ROOT, "value_usd") or 0.0
    pe_t, pe_usd = node("Polyethylene", "qty_t"), node("Polyethylene", "value_usd")
    fuels_t, fuels_v = (
        top_share("Mineral fuels", "qty_share"),
        top_share("Mineral fuels", "value_share"),
    )
    pe_note = "n/a"
    if pe_t is not None and pe_usd is not None and world_t and world_usd:
        pe_note = (
            f"{pe_t / world_t * 100:.1f} % of tonnes, {pe_usd / world_usd * 100:.1f} % of value"
        )
    return [
        {
            "label": f"World trade {year}",
            "value": f"{world_t / 1e9:,.1f} bn t",
            "note": f"{world_usd / 1e12:,.1f} trillion USD",
        },
        {
            "label": "Mineral fuels",
            "value": "n/a" if fuels_t is None else f"{fuels_t:.0f} % of tonnes",
            "note": "n/a" if fuels_v is None else f"but {fuels_v:.0f} % of value",
        },
        {
            "label": "Polyethylene",
            "value": "n/a" if pe_t is None else f"{pe_t / 1e6:,.0f} Mt",
            "note": pe_note,
        },
    ]


def shares_figure(data: AppData, year: int) -> go.Figure:
    """Share of tonnes vs. share of value per top-level class, side by side."""
    assert data.trade_by_class is not None and data.class_tree is not None
    top = classes.top_level(data.trade_by_class, data.class_tree, year)
    fig = go.Figure()
    for colour, (column, name) in zip(
        style.SERIES,
        [("qty_share", "Share of tonnes"), ("value_share", "Share of value")],
        strict=False,
    ):
        fig.add_trace(
            go.Bar(
                y=top["class"],
                x=top[column] * 100,
                name=name,
                orientation="h",
                marker={"color": colour},
                hovertemplate="%{y}: %{x:.1f} %<extra>" + name + "</extra>",
            )
        )
    fig.update_layout(barmode="group", hovermode="closest", legend={"traceorder": "normal"})
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title={"text": "% of world trade", "font": {"color": style.MUTED}})
    return charts.base_layout(fig, height=420, title=f"Tonnes vs. value by class, {year}")


PLASTICS = "Plastics in primary forms"


def treemap_figure(data: AppData, year: int) -> go.Figure:
    """Inside plastics in primary forms: polyethylene by grade next to the other plastics.

    Plastics are about 1 % of world tonnes, too small to click in a treemap of all goods,
    so this one starts at the plastics node; the bars show the world context.
    """
    assert data.trade_by_class is not None and data.class_tree is not None
    nodes = classes.drilldown(data.trade_by_class, data.class_tree, year)
    keep = {PLASTICS}
    for _ in range(3):  # the tree below plastics has two more levels
        keep |= set(nodes.loc[nodes["parent"].isin(keep), "class"])
    nodes = nodes[nodes["class"].isin(keep)].copy()
    nodes.loc[nodes["class"] == PLASTICS, "parent"] = ""
    world = float(data.trade_by_class.loc[data.trade_by_class["year"] == year, "qty_t"].sum())
    is_pe = (nodes["class"] == "Polyethylene") | (nodes["parent"] == "Polyethylene")
    fig = go.Figure(
        go.Treemap(
            ids=nodes["class"],
            labels=nodes["class"],
            parents=nodes["parent"],
            values=nodes["qty_t"],
            branchvalues="total",
            customdata=nodes["qty_t"] / 1e6,
            marker={"colors": [style.ORANGE if p else style.BLUE for p in is_pe]},
            texttemplate="%{label}<br>%{customdata:,.1f} Mt",
            hovertemplate="%{label}: %{customdata:,.1f} Mt<extra></extra>",
        )
    )
    share = nodes.loc[nodes["class"] == PLASTICS, "qty_t"].iloc[0] / world * 100 if world else 0
    return charts.base_layout(
        fig, height=420, title=f"Plastics in primary forms ({share:.1f} % of world tonnes)"
    )


def index_figure(data: AppData) -> go.Figure:
    assert data.trade_by_class is not None and data.class_tree is not None
    index = classes.indexed_tonnes(data.trade_by_class, data.class_tree, BASE_YEAR)
    order = list(classes.top_level(data.trade_by_class, data.class_tree, BASE_YEAR)["class"])
    frames = [
        (name, index[index["class"] == name].rename(columns={"year": "date", "index": "value"}))
        for name in order
    ]
    fig = go.Figure()
    for colour, (name, frame) in zip(
        style.SERIES + [style.MUTED, style.INK_SECONDARY], frames, strict=False
    ):
        fig.add_trace(
            go.Scatter(
                x=frame["date"],
                y=frame["value"],
                name=name,
                mode="lines+markers",
                line={"color": colour, "width": 2},
                hovertemplate="%{y:.0f}",
            )
        )
    fig.add_hline(y=100, line={"color": style.GRID, "width": 1})
    fig.update_yaxes(title={"text": f"tonnes, {BASE_YEAR} = 100", "font": {"color": style.MUTED}})
    fig.update_xaxes(dtick=1)
    return charts.base_layout(fig, height=340, title="Development of the classes (tonnes)")


def update(data: AppData) -> charts.Outputs:
    if data.trade_by_class is None or data.class_tree is None:
        return [], go.Figure(), go.Figure(), go.Figure()
    year = int(data.trade_by_class["year"].max())
    return (
        charts.tiles(kpi_values(data, year)),
        shares_figure(data, year),
        treemap_figure(data, year),
        index_figure(data),
    )


def register(app: Dash, state: AppState) -> None:
    if state.data.trade_by_class is None or state.data.class_tree is None:
        return

    @app.callback(
        Output("cls-kpis", "children"),
        Output("cls-shares", "figure"),
        Output("cls-treemap", "figure"),
        Output("cls-index", "figure"),
        Input("data-version", "data"),
    )
    def _update(_version: int) -> charts.Outputs:
        return update(state.data)
