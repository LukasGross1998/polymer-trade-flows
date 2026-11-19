"""Read JSON-stat 2.0 answers (Eurostat's dissemination APIs) into flat rows.

A JSON-stat dataset stores the values of an n-dimensional cube in one flat dict: the key is
the position in row-major order over the dimensions listed in `id` with the sizes in `size`.
Example: dimensions (partner, time) with sizes (2, 3): key 4 = partner 1, time 1.
"""

from typing import Any


def rows(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """One dict per value: each dimension's category code plus `value`; missing cells skipped."""
    ids: list[str] = dataset["id"]
    sizes: list[int] = dataset["size"]
    codes = []
    for dim in ids:
        index = dataset["dimension"][dim]["category"]["index"]
        by_position = (
            {position: code for code, position in index.items()}
            if isinstance(index, dict)
            else dict(enumerate(index))
        )
        codes.append(by_position)
    out = []
    for key, value in dataset.get("value", {}).items():
        position = int(key)
        cell: dict[str, Any] = {}
        for dim, size, by_position in zip(
            reversed(ids), reversed(sizes), reversed(codes), strict=True
        ):
            cell[dim] = by_position[position % size]
            position //= size
        cell["value"] = value
        out.append(cell)
    return out
