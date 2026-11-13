"""Clean CEPII BACI into the trade tables of the clean layer (ADR-009).

BACI is already reconciled: CEPII combines exporter and importer reports into one flow per
(year, exporter, importer, HS6 product), with values in thousand USD (FOB) and quantities in
tonnes. We therefore only need to

1. read the yearly CSVs from the zip and keep polyethylene (HS 3901xx),
2. translate numeric country codes to ISO3 and regions,
3. fill missing quantities (value / median unit value of the product and year, flagged),
4. sum the HS6 products to one flow per (year, exporter, importer) for the model.
"""

import io
import logging
import re
import zipfile
from pathlib import Path

import pandas as pd

from ptf.regions import RegionConfig

logger = logging.getLogger(__name__)

TRADE_HS6_COLUMNS = [
    "year",
    "exporter_iso3",
    "importer_iso3",
    "hs6",
    "product",
    "value_usd",
    "qty_t",
    "is_imputed",
    "imputation_method",
]
BILATERAL_COLUMNS = [
    "year",
    "exporter_iso3",
    "importer_iso3",
    "exporter_region",
    "importer_region",
    "value_usd",
    "qty_t",
    "imputed_qty_t",
]
IMPUTATION_METHOD = "value_div_median_unit_value"

# Short names of the polyethylene HS6 codes (HS 2017), for charts and tables.
PRODUCT_NAMES = {
    "390110": "PE, density < 0.94 (LDPE, LLDPE)",
    "390120": "PE, density >= 0.94 (HDPE)",
    "390130": "EVA copolymers",
    "390140": "Ethylene-alpha-olefin copolymers, density < 0.94",
    "390190": "Other ethylene polymers",
}

CHUNK_ROWS = 2_000_000


def _member(archive: zipfile.ZipFile, pattern: str) -> str:
    """Name of the single zip member matching `pattern` (regular expression)."""
    matches = [name for name in archive.namelist() if re.search(pattern, name)]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one file matching {pattern!r} in BACI zip, got {matches}"
        )
    return matches[0]


def read_country_codes(archive: zipfile.ZipFile) -> pd.DataFrame:
    """Columns code (int) and iso3 from the country code list in the zip."""
    with archive.open(_member(archive, r"country_codes.*\.csv$")) as file:
        codes = pd.read_csv(file, dtype=str, keep_default_na=False)
    code_column = next(c for c in codes.columns if c.lower() in ("country_code", "code"))
    iso3_column = next(c for c in codes.columns if "iso3" in c.lower())
    return pd.DataFrame(
        {"code": codes[code_column].astype(int), "iso3": codes[iso3_column].str.strip()}
    )


def read_year(archive: zipfile.ZipFile, year: int, hs_prefix: str) -> pd.DataFrame:
    """One year's flows of the products starting with `hs_prefix`, read in chunks.

    A year has around ten million rows; reading in chunks and filtering keeps memory low.
    Missing quantities are written as "NA" (sometimes padded with spaces) in the CSV.
    """
    name = _member(archive, rf"_Y{year}_V\d+\.csv$")
    parts = []
    with archive.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8")
        for chunk in pd.read_csv(text, dtype=str, chunksize=CHUNK_ROWS):
            chunk.columns = [c.strip() for c in chunk.columns]
            parts.append(chunk[chunk["k"].str.strip().str.startswith(hs_prefix)])
    year_flows = pd.concat(parts, ignore_index=True)
    return pd.DataFrame(
        {
            "year": year_flows["t"].astype(int),
            "exporter_code": year_flows["i"].astype(int),
            "importer_code": year_flows["j"].astype(int),
            "hs6": year_flows["k"].str.strip(),
            # v is in thousand USD
            "value_usd": pd.to_numeric(year_flows["v"].str.strip(), errors="coerce") * 1000,
            "qty_t": pd.to_numeric(year_flows["q"].str.strip(), errors="coerce"),
        }
    )


def extract_trade_hs6(
    zip_path: Path, years: list[int], hs_prefix: str, aliases: dict[str, str]
) -> pd.DataFrame:
    """All flows of the product group for the given years, with ISO3 codes.

    Years without a file in the zip (e.g. a year not yet published) are skipped with a warning.
    """
    with zipfile.ZipFile(zip_path) as archive:
        codes = read_country_codes(archive)
        available = [y for y in years if any(f"_Y{y}_" in n for n in archive.namelist())]
        for year in sorted(set(years) - set(available)):
            logger.warning("BACI zip has no data for %s; skipped", year)
        flows = pd.concat([read_year(archive, y, hs_prefix) for y in available], ignore_index=True)
    iso3 = dict(zip(codes["code"], codes["iso3"].replace(aliases), strict=True))
    flows["exporter_iso3"] = flows["exporter_code"].map(iso3)
    flows["importer_iso3"] = flows["importer_code"].map(iso3)
    unknown = flows["exporter_iso3"].isna() | flows["importer_iso3"].isna()
    if unknown.any():
        raise ValueError(f"{unknown.sum()} BACI rows with country codes missing in the code list")
    flows["product"] = flows["hs6"].map(PRODUCT_NAMES).fillna("other")
    return flows


def impute_quantities(flows: pd.DataFrame) -> pd.DataFrame:
    """Fill missing quantities with value / median unit value of the same HS6 and year."""
    has_qty = flows["qty_t"] > 0
    unit_value = (flows["value_usd"] / flows["qty_t"]).where(has_qty)
    median_uv = unit_value.groupby([flows["year"], flows["hs6"]]).transform("median")
    missing = ~has_qty & flows["value_usd"].gt(0) & median_uv.notna()
    flows = flows.assign(
        is_imputed=missing,
        imputation_method=missing.map({True: IMPUTATION_METHOD, False: None}),
    )
    flows.loc[missing, "qty_t"] = flows.loc[missing, "value_usd"] / median_uv[missing]
    return flows[TRADE_HS6_COLUMNS].reset_index(drop=True)


def to_bilateral_flows(trade_hs6: pd.DataFrame, regions: RegionConfig) -> pd.DataFrame:
    """Sum the HS6 products to one flow per (year, exporter, importer), with regions."""
    keys = ["year", "exporter_iso3", "importer_iso3"]
    trade = trade_hs6.assign(imputed_qty_t=trade_hs6["qty_t"].where(trade_hs6["is_imputed"], 0.0))
    flows = trade.groupby(keys, as_index=False)[["value_usd", "qty_t", "imputed_qty_t"]].sum()
    flows["exporter_region"] = flows["exporter_iso3"].map(regions.region_of)
    flows["importer_region"] = flows["importer_iso3"].map(regions.region_of)
    return flows[BILATERAL_COLUMNS]
