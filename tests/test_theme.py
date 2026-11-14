"""One design for all tabs (spec 017): theme, number formats, no developer text."""

import re

import plotly.io as pio
from helpers import REPO_ROOT
from test_ui_texts import literal_texts

from ptf.app import fmt, theme

APP_DIR = REPO_ROOT / "src" / "ptf" / "app"
COLOUR = re.compile(r"#[0-9a-fA-F]{6}\b|rgba?\(")


def test_no_tab_defines_its_own_colours() -> None:
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name == "theme.py":
            continue
        for line, text in literal_texts(path.read_text(encoding="utf-8")):
            if COLOUR.search(text):
                offenders.append(f"{path.name}:{line}: {text}")
    assert not offenders, "\n".join(offenders)


def test_status_colours_are_not_series_colours() -> None:
    status = {theme.GOOD, theme.WARNING, theme.ELEVATED, theme.CRITICAL}
    assert not status & set(theme.SERIES)
    assert theme.ROUTE_COLOURS[theme.ROUTE_AT_RISK] == theme.CRITICAL
    assert pio.templates.default == "ptf"


def test_number_formats() -> None:
    assert fmt.money(-197_400, "EUR") == "−€197k"
    assert fmt.money(1_234_000, "USD") == "$1.2m"
    assert fmt.pct(3.26) == f"+3.3{fmt.THIN}%"
    assert fmt.pct(-12.4) == f"−12{fmt.THIN}%"
    assert fmt.number(-1234) == "−1,234"
    assert fmt.span(1050, 1230) == "1,050–1,230"
    assert fmt.span(858, 858) == "858"
    assert fmt.pct_span(16, 39) == f"16–39{fmt.THIN}%"
    assert fmt.number(None) == "n/a"


def test_no_developer_text_in_the_app() -> None:
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for line, text in literal_texts(path.read_text(encoding="utf-8")):
            if "uv run" in text or "uv sync" in text or re.search(r"config/\w+\.yaml", text):
                offenders.append(f"{path.name}:{line}: {text}")
    assert not offenders, "\n".join(offenders)


def test_region_codes_are_written_out() -> None:
    assert theme.region_name("MDE") == "Middle East"
    assert theme.region_name("NAM") == "North & Central America"
    assert theme.region_name("XYZ") == "XYZ"


def test_route_states() -> None:
    assert theme.route_state(at_risk=True, delayed=True) == theme.ROUTE_AT_RISK
    assert theme.route_state(at_risk=False, delayed=True) == theme.ROUTE_DETOUR
    assert theme.route_state(False, False, sourceable=False) == theme.ROUTE_BLOCKED
    assert theme.with_alpha("#d03b3b", 0.5) == "rgba(208, 59, 59, 0.5)"
