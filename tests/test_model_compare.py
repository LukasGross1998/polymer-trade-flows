import pandas as pd
import pytest
from helpers import PipelineSetup, write_synthetic_distances

from ptf.model.compare import comparison_metrics, comparison_table
from ptf.pipeline import run_clean, run_model


def test_comparison_keeps_only_routes_between_model_regions() -> None:
    model = pd.DataFrame(
        {
            "origin_region": ["A", "A", "B"],
            "dest_region": ["A", "B", "A"],
            "qty_t": [500.0, 100.0, 0.0],
        }
    )
    observed = pd.DataFrame(
        {
            "exporter_region": ["A", "B", "ROW"],
            "importer_region": ["B", "A", "A"],
            "qty_t": [60.0, 40.0, 5.0],
        }
    )

    table = comparison_table(model, observed, ["A", "B"]).set_index(
        ["origin_region", "dest_region"]
    )

    assert set(table.index) == {("A", "B"), ("B", "A")}  # no diagonal, no ROW
    assert table.loc[("A", "B"), "model_t"] == 100.0
    assert table.loc[("B", "A"), "observed_t"] == 40.0


def test_explained_share_counts_overlap_per_route() -> None:
    table = pd.DataFrame(
        {
            "origin_region": ["A", "B"],
            "dest_region": ["B", "A"],
            "model_t": [100.0, 0.0],
            "observed_t": [60.0, 40.0],
        }
    )

    metrics = comparison_metrics(table)

    # min(100, 60) + min(0, 40) = 60 of 100 observed tonnes are on routes the model also uses
    assert metrics["explained_share"] == pytest.approx(0.6)
    assert metrics["routes_used_both"] == 1


def test_model_step_writes_layer_and_report(pipeline_setup: PipelineSetup) -> None:
    settings = pipeline_setup.settings
    run_clean(settings, pipeline_setup.regions, pipeline_setup.config)
    write_synthetic_distances(settings.raw_dir, pipeline_setup.regions)
    codes = list(pipeline_setup.regions.regions)

    run_model(settings)

    regions = pd.read_parquet(settings.model_dir / "2023" / "lp_regions.parquet")
    assert set(regions["region"]) == set(codes)
    assert regions["unmet_t"].sum() == pytest.approx(0)
    assert (settings.docs_dir / "model_results.md").exists()
