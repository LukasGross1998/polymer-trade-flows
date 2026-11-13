"""World trade by commodity class (spec 008): roll leaf classes up the class tree.

`marts.mart_trade_by_class` has one row per year and leaf class (e.g. HDPE); the tree
(`reference.commodity_class_tree`) says that HDPE belongs to Polyethylene, which belongs to
Plastics in primary forms, which belongs to All goods.
"""

import pandas as pd

ROOT = "All goods"


def top_class(tree: pd.DataFrame) -> dict[str, str]:
    """Each class -> its ancestor directly below the root (e.g. HDPE -> Plastics...)."""
    parent = dict(zip(tree["class"], tree["parent"], strict=True))
    result = {}
    for name in parent:
        node = name
        while parent.get(node) not in (ROOT, None) and pd.notna(parent.get(node)):
            node = parent[node]
        result[name] = node
    return result


def top_level(by_class: pd.DataFrame, tree: pd.DataFrame, year: int) -> pd.DataFrame:
    """Value, tonnes and shares per top-level class in one year, in the tree's order."""
    rows = by_class[by_class["year"] == year].assign(top=lambda f: f["class"].map(top_class(tree)))
    summed = rows.groupby("top", as_index=False)[
        ["value_usd", "qty_t", "value_share", "qty_share"]
    ].sum()
    order = dict(zip(tree["class"], tree["sort_order"], strict=True))
    summed = summed.rename(columns={"top": "class"})
    return summed.sort_values("class", key=lambda c: c.map(order)).reset_index(drop=True)


def indexed_tonnes(by_class: pd.DataFrame, tree: pd.DataFrame, base_year: int) -> pd.DataFrame:
    """Tonnes per top-level class and year, base year = 100. Columns: year, class, index."""
    rows = by_class.assign(top=lambda f: f["class"].map(top_class(tree)))
    yearly = rows.groupby(["top", "year"], as_index=False).agg(qty_t=("qty_t", "sum"))
    base = yearly[yearly["year"] == base_year].set_index("top")["qty_t"]
    yearly["index"] = yearly["qty_t"] / yearly["top"].map(base) * 100
    return yearly.rename(columns={"top": "class"})[["year", "class", "index"]].dropna()


def drilldown(by_class: pd.DataFrame, tree: pd.DataFrame, year: int) -> pd.DataFrame:
    """All nodes of the tree with tonnes and value (leaves summed up), for a treemap.

    Columns: class, parent, qty_t, value_usd. The root has an empty parent.
    """
    leaves = by_class[by_class["year"] == year].set_index("class")
    parent = dict(zip(tree["class"], tree["parent"], strict=True))
    totals: dict[str, list[float]] = {name: [0.0, 0.0] for name in parent}
    for name, row in leaves.iterrows():
        node: str | None = str(name)
        while node is not None and node in totals:
            totals[node][0] += float(row["qty_t"])
            totals[node][1] += float(row["value_usd"])
            up = parent.get(node)
            node = up if isinstance(up, str) and up else None
    return pd.DataFrame(
        [
            {
                "class": name,
                "parent": parent[name] if isinstance(parent[name], str) else "",
                "qty_t": qty,
                "value_usd": value,
            }
            for name, (qty, value) in totals.items()
            if qty > 0 or value > 0
        ]
    )
