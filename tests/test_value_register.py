"""Every number in config/*.yaml is in docs/value_register.md with the right class (spec 015).

A sourced fact is a mapping with `source`, `url` and `read`; any other number is a setting.
The register lists keys with `*` for one key level and `[]` for list items.
"""

import re
from collections.abc import Iterator
from fnmatch import fnmatchcase
from typing import Any

import pytest
import yaml
from helpers import REPO_ROOT

REGISTER = REPO_ROOT / "docs" / "value_register.md"
CONFIG_FILES = sorted((REPO_ROOT / "config").glob("*.yaml"))


def leaves(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """(key path, 'sourced' | 'setting') for every number or sourced mapping in a config."""
    if isinstance(node, dict):
        if {"source", "url", "read"} <= set(node):
            yield path, "sourced"
            return
        for key, value in node.items():
            yield from leaves(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for value in node:
            yield from leaves(value, f"{path}[]")
    elif isinstance(node, int | float) and not isinstance(node, bool):
        yield path, "setting"


def register() -> dict[str, list[tuple[str, str]]]:
    """Section ('sourced' / 'setting' / 'removed') -> [(file, key pattern)]."""
    rows: dict[str, list[tuple[str, str]]] = {"sourced": [], "setting": [], "removed": []}
    section = None
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = {"Sourced": "sourced", "Settings": "setting"}.get(line[3:].split()[0])
            section = section or ("removed" if line.startswith("## Removed") else None)
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if section and len(cells) >= 2 and cells[0].endswith(".yaml"):
            for key in re.findall(r"`([^`]+)`", cells[1]):
                rows[section].append((cells[0], key))
    return rows


def matches(pattern: str, path: str) -> bool:
    # fnmatch's "[" starts a character class; "[]" in the register means a list item.
    return fnmatchcase(path.replace("[]", "#"), pattern.replace("[]", "#"))


def registered_class(file: str, path: str) -> set[str]:
    return {
        section
        for section, rows in register().items()
        if section != "removed"
        for f, pattern in rows
        if f == file and matches(pattern, path)
    }


@pytest.mark.parametrize("config", CONFIG_FILES, ids=lambda p: p.name)
def test_every_config_number_is_registered_with_its_class(config: object) -> None:
    path = REPO_ROOT / "config" / str(getattr(config, "name", config))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key, kind in leaves(data):
        assert registered_class(path.name, key) == {kind}, f"{path.name}: {key} ({kind})"


def test_every_registered_key_exists() -> None:
    present = {
        (p.name, key)
        for p in CONFIG_FILES
        for key, _ in leaves(yaml.safe_load(p.read_text(encoding="utf-8")))
    }
    for section in ("sourced", "setting"):
        for file, pattern in register()[section]:
            assert any(f == file and matches(pattern, key) for f, key in present), (
                f"{file}: {pattern} is registered but not in the config"
            )
