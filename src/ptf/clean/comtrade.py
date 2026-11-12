"""Turn raw Comtrade records into the clean `trade_reports` table (schema: SPEC section 3).

One row per *report*: what one country says it imported from or exported to one partner in
one year. The same physical shipment therefore can appear twice (export report of the seller,
import report of the buyer); `ptf.clean.mirror` and `ptf.clean.reconcile` deal with that.
"""

from pathlib import Path

import numpy as np
import pandas as pd

# Comtrade flow codes we keep. Re-exports (RX) and re-imports (RM) are excluded by design.
FLOW_NAMES = {"M": "import", "X": "export"}

TRADE_REPORT_COLUMNS = [
    "year",
    "month",
    "reporter_iso3",
    "partner_iso3",
    "flow",
    "hs_code",
    "qty_t",
    "value_usd",
    "source",
    "qty_estimated_by_source",
    "is_imputed",
    "imputation_method",
]


def load_raw_comtrade(raw_dir: Path) -> pd.DataFrame:
    """Concatenate all cached reporter-year files of the raw layer."""
    files = sorted((raw_dir / "comtrade").glob("*.parquet"))
    frames = [pd.read_parquet(f) for f in files]
    frames = [f for f in frames if not f.empty]  # countries that did not report that year
    if not frames:
        raise FileNotFoundError(f"no raw Comtrade data in {raw_dir / 'comtrade'}")
    return pd.concat(frames, ignore_index=True)


def build_country_lookup(partner_areas: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    """Map Comtrade numeric area codes to ISO3 codes.

    Returns columns `code`, `iso3`, `is_group`. Comtrade uses pseudo-ISO codes for
    non-countries (e.g. "W00" World, "_X" areas nes); those are stripped of whitespace and kept
    as they are, so they later fall into the rest-of-world region. `aliases` replaces known
    pseudo codes with real countries (e.g. "S19" Other Asia nes -> TWN).
    """
    lookup = pd.DataFrame(
        {
            "code": partner_areas["PartnerCode"].astype(int),
            "iso3": partner_areas["PartnerCodeIsoAlpha3"].astype(str).str.strip(),
            "is_group": partner_areas["isGroup"].astype(bool),
        }
    )
    lookup["iso3"] = lookup["iso3"].replace(aliases)
    return lookup.drop_duplicates("code")


def to_trade_reports(raw: pd.DataFrame, country_lookup: pd.DataFrame) -> pd.DataFrame:
    """Filter, rename and convert raw records to the clean schema.

    - keeps only imports and exports, drops "World" and other aggregate partners
    - net weight kg -> tonnes; a weight of 0 or missing becomes NaN (unknown, not zero)
    - keeps Comtrade's own estimation flag in `qty_estimated_by_source`
    """
    codes = country_lookup.set_index("code")
    data = raw[raw["flowCode"].isin(FLOW_NAMES.keys())]
    # Totals only: no breakdown by second partner, customs procedure or transport mode.
    data = data[(data["partner2Code"] == 0) & (data["customsCode"] == "C00")]
    data = data[(data["motCode"] == 0) & (data["partnerCode"] != 0)]

    partner_is_group = data["partnerCode"].map(codes["is_group"]).fillna(False).astype(bool)
    # A fresh 0..n-1 index, so all new columns below line up row by row.
    data = data[~partner_is_group].reset_index(drop=True)

    weight_kg = data["netWgt"].astype(float).replace(0.0, np.nan)
    reports = pd.DataFrame(
        {
            "year": data["refYear"].astype(int),
            "month": pd.array([pd.NA] * len(data), dtype="Int64"),  # annual data: no month
            "reporter_iso3": data["reporterCode"].map(codes["iso3"]),
            "partner_iso3": data["partnerCode"].map(codes["iso3"]),
            "flow": data["flowCode"].map(FLOW_NAMES),
            "hs_code": data["cmdCode"].astype(str),
            "qty_t": weight_kg / 1000.0,
            "value_usd": data["primaryValue"].astype(float),
            "source": "comtrade",
            "qty_estimated_by_source": data["isNetWgtEstimated"].fillna(False).astype(bool),
            "is_imputed": False,
            "imputation_method": pd.Series([None] * len(data), dtype="object"),
        }
    )

    unknown = reports["reporter_iso3"].isna() | reports["partner_iso3"].isna()
    if unknown.any():
        raise ValueError(f"{unknown.sum()} rows with area codes missing in the reference table")

    duplicated = reports.duplicated(["year", "reporter_iso3", "partner_iso3", "flow", "hs_code"])
    if duplicated.any():
        raise ValueError(f"{duplicated.sum()} duplicate reports; check the raw query filters")
    return reports[TRADE_REPORT_COLUMNS]
