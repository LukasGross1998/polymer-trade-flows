"""Colours and layout styles shared by all tabs (light theme).

Palette from the data-viz guidelines: blue = observed series, gray = normal/baseline,
red <-> gray <-> blue diverging scale for "below" vs. "above normal". Status colours are only
used together with an icon and a label, never alone.
"""

SURFACE = "#fcfcfb"
PAGE_BACKGROUND = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
LAND = "#ecebe6"
BASELINE_BAND = "rgba(137, 135, 129, 0.18)"

# Categorical series colours, always assigned in this order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
BLUE, ORANGE = SERIES[0], SERIES[1]

# Diverging scale for deviation from normal.
RED = "#e34948"
NEUTRAL = "#f0efec"

# Status colours (with icon + label).
CRITICAL = "#d03b3b"
WARNING = "#fab219"
GOOD = "#006300"

PAGE = {
    "fontFamily": "-apple-system, 'Segoe UI', Roboto, sans-serif",
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
SECTION_TITLE = {"fontWeight": "600", "fontSize": "14px", "marginBottom": "4px"}
