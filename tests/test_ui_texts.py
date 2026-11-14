"""No fact as a hard-coded number in the app's texts (spec 015, criterion 5).

A number with a unit in a string literal of `ptf.app` (e.g. "Cape, 14 knots", "from 62 km/h")
must come from the config, where it has a source or is a setting. Allowed are time-window
labels ("last 7 days", "7-day average") and CSS sizes.
"""

import ast
import re

from helpers import REPO_ROOT

APP_DIR = REPO_ROOT / "src" / "ptf" / "app"
NUMBER_WITH_UNIT = re.compile(
    r"\b\d[\d,.]*\s?(knots?|kn\b|km/h|km\b|nm\b|USD|EUR|Mt\b|kt\b|m waves|t of|% of)"
)


def literal_texts(source: str) -> list[tuple[int, str]]:
    """Every string literal and literal part of an f-string, with line numbers; docstrings
    (a string as a statement of its own) are not shown in the app and are skipped."""
    tree = ast.parse(source)
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_app_texts_have_no_hard_coded_facts() -> None:
    found = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for line, text in literal_texts(path.read_text(encoding="utf-8")):
            if NUMBER_WITH_UNIT.search(text):
                found.append(f"{path.relative_to(REPO_ROOT)}:{line}: {text!r}")
    assert not found, "\n".join(found)


def test_the_check_finds_a_hard_coded_fact() -> None:
    texts = literal_texts('note = "route via the Cape, 14 knots"\nlabel = f"{x:g} knots"')
    assert [t for _, t in texts if NUMBER_WITH_UNIT.search(t)] == ["route via the Cape, 14 knots"]
