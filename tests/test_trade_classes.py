"""Commodity classes rolled up the class tree (spec 008), hand-checkable numbers."""

import pandas as pd
import pytest

from ptf.trade import classes

TREE = pd.DataFrame(
    {
        "class": [
            "All goods",
            "Mineral fuels",
            "Plastics in primary forms",
            "Polyethylene",
            "HDPE",
            "LDPE and LLDPE",
        ],
        "parent": [
            None,
            "All goods",
            "All goods",
            "Plastics in primary forms",
            "Polyethylene",
            "Polyethylene",
        ],
        "sort_order": [0, 1, 5, 1, 2, 1],
    }
)
BY_CLASS = pd.DataFrame(
    {
        "year": [2023, 2023, 2023, 2024, 2024, 2024],
        "class": ["Mineral fuels", "HDPE", "LDPE and LLDPE"] * 2,
        "qty_t": [80.0, 12.0, 8.0, 100.0, 18.0, 12.0],
        "value_usd": [40.0, 30.0, 30.0, 50.0, 40.0, 30.0],
        "value_share": [0.4, 0.3, 0.3, 50 / 120, 40 / 120, 30 / 120],
        "qty_share": [0.8, 0.12, 0.08, 100 / 130, 18 / 130, 12 / 130],
    }
)


def test_leaves_roll_up_to_top_level_classes() -> None:
    assert classes.top_class(TREE)["HDPE"] == "Plastics in primary forms"

    top = classes.top_level(BY_CLASS, TREE, 2023).set_index("class")

    assert list(top.index) == ["Mineral fuels", "Plastics in primary forms"]
    assert top.loc["Plastics in primary forms", "qty_t"] == 20.0
    assert top.loc["Plastics in primary forms", "value_share"] == pytest.approx(0.6)


def test_indexed_tonnes_and_drilldown() -> None:
    index = classes.indexed_tonnes(BY_CLASS, TREE, 2023).set_index(["class", "year"])
    assert index.loc[("Plastics in primary forms", 2024), "index"] == pytest.approx(
        150.0
    )  # 30 / 20

    nodes = classes.drilldown(BY_CLASS, TREE, 2024).set_index("class")
    assert nodes.loc["All goods", "qty_t"] == 130.0
    assert nodes.loc["Polyethylene", "qty_t"] == 30.0
    assert nodes.loc["HDPE", "parent"] == "Polyethylene"
    assert nodes.loc["All goods", "parent"] == ""
