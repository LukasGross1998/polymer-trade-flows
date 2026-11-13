"""Quality rules 3 and 4: one agreed quantity per trade relation (`bilateral_flows`).

Rule order per (year, exporter, importer), first match wins:

1. import report with a plausible unit value       (CIF, usually the more reliable side)
2. export report with a plausible unit value
3. import report even with an outlier unit value   (still a measured quantity)
4. export report even with an outlier unit value
5. impute from import value / regional unit value  (`is_imputed=True`)
6. impute from export value / regional unit value  (`is_imputed=True`)

Relations without any quantity or value are dropped. The regional unit value is the median
unit value of non-outlier reports of the reporter's region in that year and flow, with the
global median as fallback.
"""

import pandas as pd

from ptf.core.regions import RegionConfig

IMPUTATION_METHOD = "value_div_regional_unit_value"


def regional_unit_values(reports: pd.DataFrame, regions: RegionConfig) -> pd.DataFrame:
    """Median unit value per (year, flow, region of the reporter), outliers excluded.

    Includes rows with region "*" holding the global median per (year, flow) as fallback.
    """
    valid = reports[~reports["is_uv_outlier"] & reports["unit_value_usd_t"].notna()]
    valid = valid.assign(region=valid["reporter_iso3"].map(regions.region_of))
    by_region = valid.groupby(["year", "flow", "region"], as_index=False)["unit_value_usd_t"]
    global_ = valid.groupby(["year", "flow"], as_index=False)["unit_value_usd_t"]
    return pd.concat(
        [by_region.median(), global_.median().assign(region="*")], ignore_index=True
    ).rename(columns={"unit_value_usd_t": "median_uv_usd_t"})


def _lookup_unit_value(
    years: pd.Series, flow: str, regions_of_reporter: pd.Series, uv_table: pd.DataFrame
) -> pd.Series:
    """Regional median unit value for each row, falling back to the global median."""
    table = uv_table[uv_table["flow"] == flow].set_index(["year", "region"])["median_uv_usd_t"]
    regional = pd.Series(
        [table.get((y, r)) for y, r in zip(years, regions_of_reporter, strict=True)],
        index=years.index,
        dtype=float,
    )
    fallback = pd.Series([table.get((y, "*")) for y in years], index=years.index, dtype=float)
    return regional.fillna(fallback)


def reconcile_flows(
    mirror: pd.DataFrame, uv_table: pd.DataFrame, regions: RegionConfig
) -> pd.DataFrame:
    """Apply the rule order above and return one row per trade relation."""
    flows = mirror.copy()
    flows["exporter_region"] = flows["exporter_iso3"].map(regions.region_of)
    flows["importer_region"] = flows["importer_iso3"].map(regions.region_of)

    has_import = flows["qty_t_import"].notna()
    has_export = flows["qty_t_export"].notna()
    import_outlier = flows["is_uv_outlier_import"].fillna(False).astype(bool)
    export_outlier = flows["is_uv_outlier_export"].fillna(False).astype(bool)

    # Unit values needed for imputation: the importer reports imports, the exporter exports.
    uv_import = _lookup_unit_value(flows["year"], "import", flows["importer_region"], uv_table)
    uv_export = _lookup_unit_value(flows["year"], "export", flows["exporter_region"], uv_table)

    # Each rule: (condition, basis label, quantity, value). Earlier rules take precedence.
    rules = [
        (has_import & ~import_outlier, "import_report", "qty_t_import", "value_usd_import"),
        (has_export & ~export_outlier, "export_report", "qty_t_export", "value_usd_export"),
        (has_import, "import_report", "qty_t_import", "value_usd_import"),
        (has_export, "export_report", "qty_t_export", "value_usd_export"),
    ]
    flows["basis"] = pd.Series(pd.NA, index=flows.index, dtype="object")
    flows["qty_t"] = float("nan")
    flows["value_usd"] = float("nan")
    for condition, basis, qty_column, value_column in rules:
        apply = condition & flows["basis"].isna()
        flows.loc[apply, "basis"] = basis
        flows.loc[apply, "qty_t"] = flows.loc[apply, qty_column]
        flows.loc[apply, "value_usd"] = flows.loc[apply, value_column]

    # Rules 5 and 6: no quantity anywhere, but a value -> quantity = value / unit value.
    imputations = [
        ("imputed_from_import", "value_usd_import", uv_import),
        ("imputed_from_export", "value_usd_export", uv_export),
    ]
    for basis, value_column, unit_value in imputations:
        apply = flows["basis"].isna() & flows[value_column].notna() & unit_value.notna()
        flows.loc[apply, "basis"] = basis
        flows.loc[apply, "qty_t"] = flows.loc[apply, value_column] / unit_value[apply]
        flows.loc[apply, "value_usd"] = flows.loc[apply, value_column]

    flows = flows[flows["basis"].notna()].copy()
    flows["is_imputed"] = flows["basis"].str.startswith("imputed")
    flows["imputation_method"] = flows["is_imputed"].map({True: IMPUTATION_METHOD, False: None})
    from_import = flows["basis"].str.contains("import")
    flows["qty_estimated_by_source"] = (
        flows["qty_estimated_by_source_import"]
        .where(from_import, flows["qty_estimated_by_source_export"])
        .fillna(False)
        .astype(bool)
    )
    # An imputed quantity is our own estimate, not Comtrade's: Comtrade's flag on the
    # (weightless) report it came from does not apply to it.
    flows.loc[flows["is_imputed"], "qty_estimated_by_source"] = False

    columns = [
        "year",
        "exporter_iso3",
        "importer_iso3",
        "exporter_region",
        "importer_region",
        "qty_t",
        "value_usd",
        "basis",
        "is_imputed",
        "imputation_method",
        "qty_estimated_by_source",
        "qty_t_import",
        "qty_t_export",
        "qty_gap_pct",
    ]
    return flows[columns].reset_index(drop=True)
