"""Compare optimal (model) flows with observed flows between regions.

Only inter-regional flows are compared (origin != destination): trade within a region (e.g.
Germany -> France) disappears into local supply x_ii in the model.
"""

import matplotlib

matplotlib.use("Agg")
from pathlib import Path  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def comparison_table(
    model_flows: pd.DataFrame, observed: pd.DataFrame, regions: list[str]
) -> pd.DataFrame:
    """One row per inter-regional route with `model_t` and `observed_t` (0 if no flow)."""
    model = model_flows.rename(columns={"qty_t": "model_t"})[
        ["origin_region", "dest_region", "model_t"]
    ]
    seen = observed.rename(
        columns={
            "exporter_region": "origin_region",
            "importer_region": "dest_region",
            "qty_t": "observed_t",
        }
    )
    table = model.merge(seen, on=["origin_region", "dest_region"], how="outer")
    table = table[
        table["origin_region"].isin(regions)
        & table["dest_region"].isin(regions)
        & (table["origin_region"] != table["dest_region"])
    ]
    table[["model_t", "observed_t"]] = table[["model_t", "observed_t"]].fillna(0.0)
    return table.sort_values("observed_t", ascending=False).reset_index(drop=True)


def comparison_metrics(table: pd.DataFrame, threshold_t: float = 1.0) -> dict[str, float]:
    """Key figures of the fit between model and observed inter-regional trade.

    explained_share: sum of min(model, observed) / sum of observed. The part of observed trade
    that the model reproduces on the same route; 1.0 = every route exactly right.
    """
    observed_total = table["observed_t"].sum()
    overlap = np.minimum(table["model_t"], table["observed_t"]).sum()
    used_model = table["model_t"] > threshold_t
    used_observed = table["observed_t"] > threshold_t
    return {
        "observed_interregional_t": float(observed_total),
        "model_interregional_t": float(table["model_t"].sum()),
        "explained_share": float(overlap / observed_total) if observed_total else float("nan"),
        "routes_used_observed": int(used_observed.sum()),
        "routes_used_model": int(used_model.sum()),
        "routes_used_both": int((used_model & used_observed).sum()),
        "correlation": float(table["model_t"].corr(table["observed_t"])),
    }


def to_matrix(table: pd.DataFrame, column: str, regions: list[str]) -> pd.DataFrame:
    """Origin x destination matrix in kt; the diagonal stays empty (NaN)."""
    matrix = table.pivot(index="origin_region", columns="dest_region", values=column)
    return matrix.reindex(index=regions, columns=regions) / 1000


def plot_heatmaps(table: pd.DataFrame, regions: list[str], path: Path) -> None:
    """Observed and model flow matrices side by side, on the same colour scale."""
    observed = to_matrix(table, "observed_t", regions)
    model = to_matrix(table, "model_t", regions)
    vmax = float(np.nanmax([observed.to_numpy(), model.to_numpy()]))

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for ax, matrix, title in [(axes[0], observed, "Observed"), (axes[1], model, "Model (LP)")]:
        image = ax.imshow(matrix.to_numpy(), cmap="Blues", vmin=0, vmax=vmax)
        ax.set_xticks(range(len(regions)), regions)
        ax.set_yticks(range(len(regions)), regions)
        ax.set_xlabel("to (importing region)")
        ax.set_ylabel("from (exporting region)")
        ax.set_title(f"{title}, kt")
        values = matrix.to_numpy(dtype=float)
        for i in range(len(regions)):
            for j in range(len(regions)):
                value = values[i, j]
                if not np.isnan(value) and value >= 50:
                    colour = "white" if value > vmax / 2 else "black"
                    ax.text(
                        j, i, f"{value:,.0f}", ha="center", va="center", fontsize=6, color=colour
                    )
    fig.colorbar(image, ax=axes, shrink=0.8)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
