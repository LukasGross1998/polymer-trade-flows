"""Quality rules 1-4 on tiny hand-made examples whose results can be checked by hand."""

import math

import pandas as pd
import pytest

from ptf.core.regions import RegionConfig
from ptf.legacy.comtrade.mirror import build_mirror_table, qty_gap_pct
from ptf.legacy.comtrade.quality import add_unit_values, flag_unit_value_outliers
from ptf.legacy.comtrade.reconcile import IMPUTATION_METHOD, reconcile_flows, regional_unit_values

REGIONS = RegionConfig.model_validate(
    {
        "rest_of_world": "ROW",
        "regions": {
            "EUR": {"name": "E", "port": {"name": "p", "lon": 0, "lat": 0}, "reporters": ["DEU"]},
            "NAM": {"name": "N", "port": {"name": "p", "lon": 0, "lat": 0}, "reporters": ["USA"]},
        },
    }
)


def report(reporter: str, partner: str, flow: str, qty_t: float | None, value: float) -> dict:
    return {
        "year": 2023,
        "reporter_iso3": reporter,
        "partner_iso3": partner,
        "flow": flow,
        "qty_t": qty_t,
        "value_usd": value,
        "qty_estimated_by_source": False,
    }


def prepared(rows: list[dict], threshold: float = 3.0) -> pd.DataFrame:
    reports = pd.DataFrame(rows).astype({"qty_t": float})
    return flag_unit_value_outliers(add_unit_values(reports), threshold)


# --- rule 1: unit values and outliers ------------------------------------------------------


def test_unit_value_is_value_per_tonne() -> None:
    reports = add_unit_values(pd.DataFrame([report("DEU", "USA", "import", 100.0, 120_000.0)]))

    assert reports.loc[0, "unit_value_usd_t"] == pytest.approx(1_200.0)


def test_unit_value_is_nan_without_quantity() -> None:
    reports = add_unit_values(pd.DataFrame([report("DEU", "USA", "import", None, 120_000.0)]))

    assert math.isnan(reports.loc[0, "unit_value_usd_t"])


def test_kg_reported_as_tonnes_is_flagged_as_outlier() -> None:
    # Five normal prices of 1,100-1,300 USD/t and one with a 1000x too high quantity.
    reports = prepared(
        [
            report("DEU", "A", "import", 100.0, 110_000.0),
            report("DEU", "B", "import", 100.0, 120_000.0),
            report("DEU", "C", "import", 100.0, 120_000.0),
            report("DEU", "D", "import", 100.0, 130_000.0),
            report("DEU", "E", "import", 100.0, 125_000.0),
            report("DEU", "F", "import", 100_000.0, 125_000.0),  # 1.25 USD/t: kg as tonnes
        ]
    )

    assert reports["is_uv_outlier"].tolist() == [False] * 5 + [True]


# --- rule 2: mirror statistics -------------------------------------------------------------


def test_symmetric_gap() -> None:
    gap = qty_gap_pct(pd.Series([110.0]), pd.Series([90.0]))

    assert gap.iloc[0] == pytest.approx(20.0)  # (110 - 90) / 100


def test_mirror_table_pairs_export_and_import_report() -> None:
    reports = prepared(
        [
            report("USA", "DEU", "export", 90.0, 100_000.0),  # USA says: shipped 90 t
            report("DEU", "USA", "import", 110.0, 130_000.0),  # DEU says: received 110 t
            report("DEU", "NGA", "export", 50.0, 60_000.0),  # NGA does not report
        ]
    )

    mirror = build_mirror_table(reports).set_index(["exporter_iso3", "importer_iso3"])

    usa_deu = mirror.loc[("USA", "DEU")]
    assert usa_deu["has_both_reports"]
    assert usa_deu["qty_gap_pct"] == pytest.approx(20.0)
    assert usa_deu["cif_fob_ratio"] == pytest.approx(1.3)
    assert not mirror.loc[("DEU", "NGA"), "has_both_reports"]


# --- rules 3 and 4: reconciliation ---------------------------------------------------------


def reconcile(rows: list[dict]) -> pd.DataFrame:
    reports = prepared(rows)
    mirror = build_mirror_table(reports)
    return reconcile_flows(mirror, regional_unit_values(reports, REGIONS), REGIONS)


def test_import_report_is_preferred() -> None:
    flows = reconcile(
        [
            report("USA", "DEU", "export", 90.0, 100_000.0),
            report("DEU", "USA", "import", 110.0, 130_000.0),
        ]
    )

    row = flows.iloc[0]
    assert row["basis"] == "import_report"
    assert row["qty_t"] == 110.0
    assert not row["is_imputed"]
    assert (row["exporter_region"], row["importer_region"]) == ("NAM", "EUR")


def test_export_report_is_fallback_when_importer_does_not_report() -> None:
    flows = reconcile([report("DEU", "NGA", "export", 50.0, 60_000.0)])

    assert flows.iloc[0]["basis"] == "export_report"
    assert flows.iloc[0]["importer_region"] == "ROW"


def test_missing_quantity_is_imputed_from_regional_unit_value() -> None:
    flows = reconcile(
        [
            # Two DEU import reports with quantities give EUR a median import price of 1,200.
            report("DEU", "USA", "import", 100.0, 120_000.0),
            report("DEU", "FRA", "import", 100.0, 120_000.0),
            # Value without weight: 60,000 USD / 1,200 USD/t = 50 t.
            report("DEU", "CHN", "import", None, 60_000.0)
            | {"qty_estimated_by_source": True},  # Comtrade flag on a report without weight
        ]
    ).set_index("exporter_iso3")

    imputed = flows.loc["CHN"]
    assert imputed["is_imputed"]
    assert not imputed["qty_estimated_by_source"]
    assert imputed["imputation_method"] == IMPUTATION_METHOD
    assert imputed["qty_t"] == pytest.approx(50.0)
    assert not flows.loc["USA", "is_imputed"]
