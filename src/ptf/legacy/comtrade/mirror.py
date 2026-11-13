"""Quality rule 2: mirror statistics.

Every shipment can be reported twice: as an export by the seller and as an import by the
buyer. This module puts both reports of the same trade relation side by side, one row per
(year, exporter, importer), and measures how far they disagree.

We compare *quantities*: import values include freight and insurance (CIF), export values do
not (FOB), so values differ systematically even when both reports are correct.
"""

import pandas as pd

SIDE_COLUMNS = ["qty_t", "value_usd", "qty_estimated_by_source", "is_uv_outlier"]


def build_mirror_table(reports: pd.DataFrame) -> pd.DataFrame:
    """Outer join of export reports and import reports of the same trade relation.

    Expects `reports` with unit-value flags (see `quality` in this package). A missing side means
    that country did not report this relation (or is not among our reporters).
    """
    exports = reports[reports["flow"] == "export"].rename(
        columns={"reporter_iso3": "exporter_iso3", "partner_iso3": "importer_iso3"}
    )
    imports = reports[reports["flow"] == "import"].rename(
        columns={"reporter_iso3": "importer_iso3", "partner_iso3": "exporter_iso3"}
    )
    keys = ["year", "exporter_iso3", "importer_iso3"]
    exports = exports[keys + SIDE_COLUMNS].add_suffix("_export")
    imports = imports[keys + SIDE_COLUMNS].add_suffix("_import")

    mirror = exports.merge(
        imports,
        left_on=[k + "_export" for k in keys],
        right_on=[k + "_import" for k in keys],
        how="outer",
    )
    # After an outer join each key exists on one side or both: combine into one column.
    for key in keys:
        mirror[key] = mirror[key + "_export"].fillna(mirror[key + "_import"])
        mirror = mirror.drop(columns=[key + "_export", key + "_import"])

    mirror = mirror[mirror["exporter_iso3"] != mirror["importer_iso3"]]
    mirror["year"] = mirror["year"].astype(int)
    mirror["has_both_reports"] = mirror["qty_t_export"].notna() & mirror["qty_t_import"].notna()
    mirror["qty_gap_pct"] = qty_gap_pct(mirror["qty_t_import"], mirror["qty_t_export"])
    mirror["cif_fob_ratio"] = mirror["value_usd_import"] / mirror["value_usd_export"]
    return mirror[keys + [c for c in mirror.columns if c not in keys]].reset_index(drop=True)


def qty_gap_pct(qty_import: pd.Series, qty_export: pd.Series) -> pd.Series:
    """Symmetric percentage gap: (import - export) / average of both, in percent.

    Symmetric means swapping the two sides only flips the sign, and the result is bounded by
    +-200 %. NaN when either side is missing.
    """
    average = (qty_import + qty_export) / 2
    return (qty_import - qty_export) / average * 100
