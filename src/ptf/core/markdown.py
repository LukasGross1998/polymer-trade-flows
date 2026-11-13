"""Small Markdown helpers for the generated reports (`docs/*.md`)."""

import pandas as pd


def to_markdown(table: pd.DataFrame, decimals: int = 1) -> str:
    """Minimal Markdown table writer (avoids an extra dependency for `DataFrame.to_markdown`)."""

    def fmt(value: object) -> str:
        if isinstance(value, float):
            return f"{value:,.{decimals}f}"
        return str(value)

    header = "| " + " | ".join(str(c) for c in table.columns) + " |"
    divider = "|" + "|".join("---" for _ in table.columns) + "|"
    rows = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join([header, divider, *rows])
