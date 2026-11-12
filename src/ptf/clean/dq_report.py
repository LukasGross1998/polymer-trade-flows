"""Quality rule 5: data-quality report (coverage, mirror gaps, imputation share).

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
import pandas as pd  # noqa: E402

from ptf.ingest.comtrade import raw_path  # noqa: E402

# --- tables --------------------------------------------------------------------------------


def coverage_table(
    reports_path: Path, raw_dir: Path, reporters: list[str], years: list[int]
) -> pd.DataFrame:
    """Partner reports per reporter (rows) and year (columns) for all expected reporters.

    Three states per cell:
    - a positive count: the country reported
    - 0: we asked Comtrade, but the country has no data for that year
    - <NA>: not downloaded yet (e.g. stopped by the daily API quota)
    """
    long = duckdb.sql(
        f"""
        SELECT reporter_iso3, year, count(*) AS reports
        FROM read_parquet('{reports_path}')
        GROUP BY reporter_iso3, year
        """
    ).df()
    counts = (
        long.pivot(index="reporter_iso3", columns="year", values="reports")
        .reindex(index=sorted(reporters), columns=years)
        .astype("Int64")
    )
    for iso3 in counts.index:
        for year in years:
            fetched = raw_path(raw_dir, iso3, year).exists()
            if pd.isna(counts.loc[iso3, year]) and fetched:
                counts.loc[iso3, year] = 0
    return counts


def mirror_summary(mirror: pd.DataFrame) -> pd.DataFrame:
    """Per year: how many relations are reported by both sides and how well they agree."""
    both = mirror[mirror["has_both_reports"]].assign(abs_gap=lambda d: d["qty_gap_pct"].abs())
    summary = both.groupby("year").agg(
        relations_with_both_reports=("abs_gap", "size"),
        median_abs_gap_pct=("abs_gap", "median"),
        share_within_10pct=("abs_gap", lambda s: (s <= 10).mean() * 100),
        share_within_25pct=("abs_gap", lambda s: (s <= 25).mean() * 100),
        median_cif_fob_ratio=("cif_fob_ratio", "median"),
    )
    total = mirror.groupby("year").size().rename("relations_total")
    return pd.concat([total, summary], axis=1).reset_index()


def basis_share(flows: pd.DataFrame) -> pd.DataFrame:
    """Share of traded tonnes per year by source of the agreed quantity, in percent."""
    tonnes = flows.pivot_table(
        index="year", columns="basis", values="qty_t", aggfunc="sum", fill_value=0
    )
    share = tonnes.div(tonnes.sum(axis=1), axis=0) * 100
    share["estimated_by_comtrade"] = (
        flows[flows["qty_estimated_by_source"]].groupby("year")["qty_t"].sum()
        / flows.groupby("year")["qty_t"].sum()
        * 100
    )
    return share.fillna(0).reset_index()


def outlier_summary(reports: pd.DataFrame) -> pd.DataFrame:
    """Per year and flow: reports with a unit value, outliers, and the median unit value.

    Outliers are counted *and* weighted by tonnes: many outliers are tiny lots (samples,
    specialty grades) that matter little for the volumes.
    """
    with_uv = reports[reports["unit_value_usd_t"].notna()].assign(
        outlier_t=lambda d: d["qty_t"].where(d["is_uv_outlier"], 0.0)
    )
    summary = (
        with_uv.groupby(["year", "flow"])
        .agg(
            reports_with_unit_value=("unit_value_usd_t", "size"),
            outliers=("is_uv_outlier", "sum"),
            outlier_t=("outlier_t", "sum"),
            total_t=("qty_t", "sum"),
            median_unit_value_usd_t=("unit_value_usd_t", "median"),
        )
        .reset_index()
    )
    summary["outlier_tonnage_pct"] = summary["outlier_t"] / summary["total_t"] * 100
    return summary.drop(columns=["outlier_t", "total_t"])


def region_matrix(flows_path: Path, year: int) -> pd.DataFrame:
    """Inter-regional trade in kt for one year (rows: exporter region, columns: importer)."""
    long = duckdb.sql(
        f"""
        SELECT exporter_region, importer_region, sum(qty_t) / 1000 AS kt
        FROM read_parquet('{flows_path}')
        WHERE year = {int(year)} AND exporter_region <> importer_region
        GROUP BY exporter_region, importer_region
        """
    ).df()
    return long.pivot(index="exporter_region", columns="importer_region", values="kt").fillna(0)


def largest_mirror_gaps(mirror: pd.DataFrame, year: int, n: int = 10) -> pd.DataFrame:
    """Relations with the largest absolute disagreement in tonnes for one year."""
    both = mirror[(mirror["year"] == year) & mirror["has_both_reports"]].copy()
    both["gap_t"] = both["qty_t_import"] - both["qty_t_export"]
    both = both.reindex(both["gap_t"].abs().sort_values(ascending=False).index).head(n)
    return both[
        ["exporter_iso3", "importer_iso3", "qty_t_export", "qty_t_import", "gap_t", "qty_gap_pct"]
    ]


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


def _plot_coverage(coverage: pd.DataFrame, path: Path) -> None:
    # Colour codes: 2 = reported, 1 = no data at Comtrade, 0 = not downloaded yet.
    state = coverage.notna().astype(int) + (coverage.fillna(0) > 0).astype(int)
    colours = matplotlib.colors.ListedColormap(["#d9d9d9", "#f4a582", "#5aae61"])
    fig, ax = plt.subplots(figsize=(6, 10))
    ax.imshow(state.to_numpy(), cmap=colours, aspect="auto", vmin=0, vmax=2)
    ax.set_xticks(range(len(coverage.columns)), [str(c) for c in coverage.columns])
    ax.set_yticks(range(len(coverage.index)), coverage.index)
    for i, iso3 in enumerate(coverage.index):
        for j, year in enumerate(coverage.columns):
            value = coverage.loc[iso3, year]
            label = "n/f" if pd.isna(value) else str(value)
            ax.text(j, i, label, ha="center", va="center", fontsize=7)
    ax.set_title(
        "Reports per reporter and year\n(green: reported, red: no data, grey: not fetched)"
    )
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_mirror_gaps(mirror: pd.DataFrame, path: Path) -> None:
    gaps = mirror.loc[mirror["has_both_reports"], "qty_gap_pct"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(gaps, bins=40, range=(-200, 200), color="#4c72b0")
    ax.axvline(0, color="black", linewidth=1)
    ax.set_xlabel("Import vs. export report, quantity gap in % (symmetric)")
    ax.set_ylabel("Trade relations")
    ax.set_title("Mirror statistics: how much do both sides disagree?")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_basis_share(share: pd.DataFrame, path: Path) -> None:
    columns = [c for c in share.columns if c not in ("year", "estimated_by_comtrade")]
    fig, ax = plt.subplots(figsize=(7, 4))
    share.plot.bar(x="year", y=columns, stacked=True, ax=ax)
    ax.set_ylabel("% of traded tonnes")
    ax.set_title("Where does the agreed quantity come from?")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def build_report(
    clean_dir: Path, docs_dir: Path, raw_dir: Path, reporters: list[str], years: list[int]
) -> Path:
    """Compute all tables and charts and write the Markdown report. Returns its path."""
    reports_path = clean_dir / "trade_reports.parquet"
    flows_path = clean_dir / "bilateral_flows.parquet"
    reports = pd.read_parquet(reports_path)
    mirror = pd.read_parquet(clean_dir / "mirror.parquet")
    flows = pd.read_parquet(flows_path)
    latest_year = int(flows["year"].max())

    coverage = coverage_table(reports_path, raw_dir, reporters, years)
    mirror_stats = mirror_summary(mirror)
    shares = basis_share(flows)
    outliers = outlier_summary(reports)
    matrix = region_matrix(flows_path, latest_year)
    top_gaps = largest_mirror_gaps(mirror, latest_year)

    figures = docs_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    _plot_coverage(coverage, figures / "dq_coverage.png")
    _plot_mirror_gaps(mirror, figures / "dq_mirror_gaps.png")
    _plot_basis_share(shares, figures / "dq_basis_share.png")

    sections = [
        "# Data-quality report (generated)",
        "Generated by `uv run python -m ptf.pipeline report`. Do not edit by hand.",
        "Method and rules: [methodology.md](methodology.md).",
        "## 1. Coverage: reports per reporter and year",
        "![coverage](figures/dq_coverage.png)",
        "`<NA>` = not downloaded yet, 0 = Comtrade has no data for this reporter and year.",
        to_markdown(coverage.reset_index()),
        "## 2. Mirror statistics (quantities)",
        "![mirror gaps](figures/dq_mirror_gaps.png)",
        to_markdown(mirror_stats),
        f"### Largest disagreements in {latest_year} (tonnes)",
        to_markdown(top_gaps, decimals=0),
        "## 3. Source of the agreed quantity (% of tonnes)",
        "![basis share](figures/dq_basis_share.png)",
        to_markdown(shares),
        "## 4. Unit values and outliers",
        to_markdown(outliers),
        f"## 5. Inter-regional trade {latest_year} (kt, rows export, columns import)",
        to_markdown(matrix.reset_index(), decimals=0),
    ]
    path = docs_dir / "data_quality.md"
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return path
