"""Data-quality report of the trade data (BACI), with a check against our own Comtrade work.

Reads the clean layer, computes summary tables and writes:
- `docs/data_quality.md` with all tables (Markdown, readable on GitHub)
- `docs/figures/dq_*.png` charts

Aggregations over the Parquet files use DuckDB SQL, the "query engine on files" part of the
lakehouse setup; the small result tables are then handled in pandas.
"""

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")  # render to files, no window needed (works in CI and Docker)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SERIES_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]

# --- tables --------------------------------------------------------------------------------


def _query(sql: str) -> pd.DataFrame:
    """Run SQL on an in-memory DuckDB connection and return the result as a DataFrame."""
    with duckdb.connect() as connection:
        return connection.execute(sql).df()


def coverage_by_year(hs6_path: Path) -> pd.DataFrame:
    """Per year: exporters, importers, flows and total traded tonnes."""
    return _query(
        f"""
        SELECT year,
               count(DISTINCT exporter_iso3) AS exporters,
               count(DISTINCT importer_iso3) AS importers,
               count(*) AS hs6_flows,
               sum(qty_t) / 1e6 AS traded_mt
        FROM read_parquet('{hs6_path}')
        GROUP BY year ORDER BY year
        """
    )


def tonnes_by_product(trade_hs6: pd.DataFrame) -> pd.DataFrame:
    """Traded million tonnes per year (rows) and HS6 product (columns)."""
    table = trade_hs6.pivot_table(
        index="year", columns="product", values="qty_t", aggfunc="sum", fill_value=0
    )
    return (table / 1e6).reset_index()


def imputation_share(trade_hs6: pd.DataFrame) -> pd.DataFrame:
    """Per year: flows and tonnes whose quantity was imputed from the value."""
    grouped = trade_hs6.groupby("year")
    imputed_t = trade_hs6["qty_t"].where(trade_hs6["is_imputed"], 0.0).groupby(trade_hs6["year"])
    return pd.DataFrame(
        {
            "flows": grouped.size(),
            "imputed_flows": grouped["is_imputed"].sum(),
            "imputed_tonnage_pct": imputed_t.sum() / grouped["qty_t"].sum() * 100,
        }
    ).reset_index()


def unit_values(trade_hs6: pd.DataFrame) -> pd.DataFrame:
    """Median unit value (USD/t, FOB) per year and product, from flows with a reported weight."""
    reported = trade_hs6[~trade_hs6["is_imputed"] & (trade_hs6["qty_t"] > 0)]
    uv = (reported["value_usd"] / reported["qty_t"]).rename("usd_t")
    table = (
        pd.concat([reported[["year", "product"]], uv], axis=1)
        .pivot_table(index="year", columns="product", values="usd_t", aggfunc="median")
        .round(0)
    )
    return table.reset_index()


def region_matrix(flows_path: Path, year: int) -> pd.DataFrame:
    """Inter-regional trade in kt for one year (rows: exporter region, columns: importer)."""
    long = _query(
        f"""
        SELECT exporter_region, importer_region, sum(qty_t) / 1000 AS kt
        FROM read_parquet('{flows_path}')
        WHERE year = {int(year)} AND exporter_region <> importer_region
        GROUP BY exporter_region, importer_region
        """
    )
    return long.pivot(index="exporter_region", columns="importer_region", values="kt").fillna(0)


def compare_with_comtrade(baci: pd.DataFrame, comtrade: pd.DataFrame) -> pd.DataFrame:
    """Relations present in both BACI and our own Comtrade reconciliation, side by side.

    Columns: year, exporter_iso3, importer_iso3, qty_t_baci, qty_t_comtrade, gap_pct
    (symmetric: (Comtrade - BACI) / mean of both).
    """
    keys = ["year", "exporter_iso3", "importer_iso3"]
    both = baci[keys + ["qty_t"]].merge(
        comtrade[keys + ["qty_t"]], on=keys, suffixes=("_baci", "_comtrade")
    )
    both = both[(both["qty_t_baci"] > 0) & (both["qty_t_comtrade"] > 0)]
    mean = (both["qty_t_baci"] + both["qty_t_comtrade"]) / 2
    both["gap_pct"] = (both["qty_t_comtrade"] - both["qty_t_baci"]) / mean * 100
    return both.reset_index(drop=True)


def comparison_summary(both: pd.DataFrame) -> pd.DataFrame:
    """How close our Comtrade reconciliation came to BACI, per year."""
    abs_gap = both["gap_pct"].abs()
    grouped = abs_gap.groupby(both["year"])
    tonnes = both.groupby("year")[["qty_t_baci", "qty_t_comtrade"]].sum() / 1000
    return pd.DataFrame(
        {
            "relations_in_both": grouped.size(),
            "median_abs_gap_pct": grouped.median(),
            "share_within_10pct": grouped.apply(lambda s: (s <= 10).mean() * 100),
            "kt_baci": tonnes["qty_t_baci"],
            "kt_comtrade": tonnes["qty_t_comtrade"],
        }
    ).reset_index()


# --- output --------------------------------------------------------------------------------


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


def _plot_products(by_product: pd.DataFrame, path: Path) -> None:
    products = [c for c in by_product.columns if c != "year"]
    fig, ax = plt.subplots(figsize=(8, 4))
    bottom = np.zeros(len(by_product))
    for colour, product in zip(SERIES_COLOURS, products, strict=False):
        ax.bar(by_product["year"], by_product[product], bottom=bottom, label=product, color=colour)
        bottom += by_product[product].to_numpy()
    ax.set_ylabel("Million tonnes traded")
    ax.set_title("World polyethylene trade by product (BACI, HS 3901)")
    ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1, 1))
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_comparison(both: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.scatter(both["qty_t_baci"], both["qty_t_comtrade"], s=6, alpha=0.4, color="#2a78d6")
    low, high = 1, max(both["qty_t_baci"].max(), both["qty_t_comtrade"].max())
    ax.plot([low, high], [low, high], color="#52514e", linewidth=1)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("BACI (t)")
    ax.set_ylabel("Our Comtrade reconciliation (t)")
    ax.set_title("Same relation, two sources (line = identical)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def build_report(clean_dir: Path, docs_dir: Path) -> Path:
    """Compute all tables and charts and write the Markdown report. Returns its path."""
    hs6_path = clean_dir / "trade_hs6.parquet"
    flows_path = clean_dir / "bilateral_flows.parquet"
    trade_hs6 = pd.read_parquet(hs6_path)
    flows = pd.read_parquet(flows_path)
    latest_year = int(flows["year"].max())

    figures = docs_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    by_product = tonnes_by_product(trade_hs6)
    _plot_products(by_product, figures / "dq_products.png")

    sections = [
        "# Data-quality report (generated)",
        "Generated by `uv run python -m ptf.pipeline report`. Do not edit by hand. "
        "Source: CEPII BACI (reconciled UN Comtrade data), see "
        "[methodology.md](methodology.md) and ADR-009.",
        "## 1. Coverage",
        to_markdown(coverage_by_year(hs6_path)),
        "## 2. Traded tonnes by product (Mt)",
        "![products](figures/dq_products.png)",
        to_markdown(by_product, decimals=2),
        "## 3. Missing quantities (imputed as value / median unit value)",
        to_markdown(imputation_share(trade_hs6)),
        "## 4. Median unit values, USD/t (FOB, flows with reported weight)",
        to_markdown(unit_values(trade_hs6), decimals=0),
        f"## 5. Inter-regional trade {latest_year} (kt, rows export, columns import)",
        to_markdown(region_matrix(flows_path, latest_year).reset_index(), decimals=0),
    ]

    comtrade_path = clean_dir / "comtrade_flows.parquet"
    if comtrade_path.exists():
        both = compare_with_comtrade(flows, pd.read_parquet(comtrade_path))
        _plot_comparison(both, figures / "dq_baci_vs_comtrade.png")
        sections += [
            "## 6. Check: BACI vs. our own Comtrade reconciliation",
            "Relations covered by both (our Comtrade download covers 17 reporters; ADR-009). "
            "Gap = (Comtrade − BACI) / mean of both.",
            "![comparison](figures/dq_baci_vs_comtrade.png)",
            to_markdown(comparison_summary(both)),
        ]

    path = docs_dir / "data_quality.md"
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return path
