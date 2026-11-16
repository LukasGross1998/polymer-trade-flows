"""One design for all tabs (spec 017): colours, route encoding, Plotly template, building blocks.

Colours carry one meaning each:
- status colours (ok / watch / elevated / critical) only for status, always with icon + word;
- the categorical palette for data series and cost components, in a fixed order. It has no
  red, orange, yellow or green, so a series never looks like a status. Validated with the
  data-viz palette validator (light surface #fcfcfb): lightness band, chroma, colour-blind
  separation (worst adjacent ΔE 19.9) and normal vision (24.0) pass; aqua and magenta are
  below 3:1 contrast, so charts using them carry a legend or direct labels;
- the route encoding (open / detour / at risk / not sourceable) is the same in every chart
  that shows origins or routes.
"""

import plotly.graph_objects as go
import plotly.io as pio
from dash import html
from dash.development.base_component import Component

# --- surfaces and ink ------------------------------------------------------------------------
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
SURFACE = "#fcfcfb"
PAGE_BACKGROUND = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
LAND = "#ecebe6"
BASELINE_BAND = "rgba(137, 135, 129, 0.18)"

# --- categorical palette: data series and cost components, always in this order -----------------
SERIES = ["#2a78d6", "#1baf7a", "#6250d6", "#e87ba4", "#184f95"]
BLUE, AQUA, VIOLET, MAGENTA, DARK_BLUE = SERIES
HIGHLIGHT = VIOLET  # one selected item among many (e.g. the selected country)

# Diverging scale (below / above normal): red <-> gray <-> blue, gray midpoint.
DIVERGING_LOW = "#e34948"
NEUTRAL = "#f0efec"
DIVERGING_HIGH = BLUE

# --- status colours: only with an icon and a word ----------------------------------------------
GOOD = "#006300"
WARNING = "#fab219"
ELEVATED = "#e0701b"
CRITICAL = "#d03b3b"

# --- route encoding (specs 014, 016) ---------------------------------------------------------
ROUTE_OPEN = "open"
ROUTE_DETOUR = "detour"
ROUTE_AT_RISK = "at risk"
ROUTE_BLOCKED = "not sourceable"
ROUTE_COLOURS = {
    ROUTE_OPEN: "rgba(137, 135, 129, 0.45)",
    ROUTE_DETOUR: ELEVATED,
    ROUTE_AT_RISK: CRITICAL,
    ROUTE_BLOCKED: GRID,
}
ROUTE_ICONS = {ROUTE_OPEN: "●", ROUTE_DETOUR: "↻", ROUTE_AT_RISK: "⚠", ROUTE_BLOCKED: "⊘"}


def route_state(at_risk: bool, delayed: bool, sourceable: bool = True) -> str:
    """The route encoding of one origin: not sourceable wins, then at risk, then detour."""
    if not sourceable:
        return ROUTE_BLOCKED
    if at_risk:
        return ROUTE_AT_RISK
    if delayed:
        return ROUTE_DETOUR
    return ROUTE_OPEN


def with_alpha(colour: str, alpha: float) -> str:
    """'#d03b3b' -> 'rgba(208, 59, 59, 0.5)'; rgba colours keep their own alpha."""
    if not colour.startswith("#"):
        return colour
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def route_label(state: str) -> str:
    return f"{ROUTE_ICONS[state]} {state}"


# --- abbreviations written out (spec 017) -------------------------------------------------------
REGION_NAMES = {
    "NAM": "North & Central America",
    "SAM": "South America",
    "EUR": "Europe",
    "CIS": "Russia & CIS",
    "MDE": "Middle East",
    "AFR": "Africa",
    "IND": "India & South Asia",
    "CHN": "China",
    "NEA": "Northeast Asia",
    "SEA": "Southeast Asia",
    "ROW": "Rest of world",
}
GLOSSARY = {
    "nm": "nautical miles",
    "kt": "thousand tonnes",
    "TEU": "twenty-foot equivalent unit (container size)",
    "FOB": "free on board: price at the export port, without freight",
    "CIF": "cost, insurance and freight: the EU customs value",
}


def region_name(code: str) -> str:
    return REGION_NAMES.get(code, code)


# --- layout styles -----------------------------------------------------------------------------
PAGE = {
    "fontFamily": FONT,
    "backgroundColor": PAGE_BACKGROUND,
    "color": INK,
    "padding": "16px 24px",
    "maxWidth": "1280px",
    "margin": "0 auto",
}
CARD = {
    "backgroundColor": SURFACE,
    "border": f"1px solid {GRID}",
    "borderRadius": "8px",
    "padding": "12px 16px",
}
ROW = {"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "16px"}
CONTROL = {"minWidth": "220px", "flex": "1"}
SMALL_NOTE = {"fontSize": "12px", "color": MUTED, "marginTop": "8px"}
SECTION_TITLE = {"fontWeight": "600", "fontSize": "14px", "marginBottom": "4px", "color": INK}
CARD_TITLE = {"fontWeight": "600", "fontSize": "14px", "color": INK, "margin": "0 0 4px 0"}

# --- Plotly template: the default for every figure ---------------------------------------------
TEMPLATE = go.layout.Template(
    layout=go.Layout(
        font={"family": FONT, "color": INK_SECONDARY, "size": 12},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=SERIES,
        hoverlabel={"font": {"family": FONT}},
        xaxis={
            "showgrid": False,
            "linecolor": GRID,
            "tickfont": {"color": MUTED},
            "automargin": True,
        },
        yaxis={
            "gridcolor": GRID,
            "zeroline": False,
            "tickfont": {"color": MUTED},
            "automargin": True,
        },
        legend={"orientation": "h", "y": -0.22, "x": 0, "yanchor": "top"},
        separators=".,",
    )
)
pio.templates["ptf"] = TEMPLATE
pio.templates.default = "ptf"


# --- building blocks -----------------------------------------------------------------------------
def info(text: str) -> html.Span:
    """The (i) icon with a hover text."""
    return html.Span(
        " ⓘ",
        title=text,
        style={"color": MUTED, "cursor": "help", "fontWeight": "400"},
    )


def method_panel(text: str | list[Component | str], title: str = "Method and sources") -> Component:
    """A collapsed panel behind an (i) for a tab's method notes, sources and data dates."""
    return html.Details(
        [
            html.Summary(
                ["ⓘ ", title],
                style={"cursor": "pointer", "color": INK_SECONDARY, "fontSize": "13px"},
            ),
            html.Div(text, style={**SMALL_NOTE, "marginTop": "6px"}),
        ],
        style={"marginBottom": "16px"},
    )
