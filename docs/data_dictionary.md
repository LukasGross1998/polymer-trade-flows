# Data dictionary

Every table of the data lake, every column: meaning, unit, origin and an example value.
Rules and reasoning behind the columns: [methodology.md](methodology.md). Current numbers:
[data_quality.md](data_quality.md).

`tests/test_data_dictionary.py` checks that the column lists below match the tables the
pipeline actually writes, so this page cannot silently drift from the code.

## Overview

```
raw (unchanged sources)               clean (prepared)
─────────────────────────────────     ─────────────────────────────────────────────
comtrade/{ISO3}_{year}.parquet   ──►  trade_reports    one row per report
comtrade_reference/*.parquet     ──┘        │
                                            ▼
                                      mirror           export + import report side by side
                                            │
                                            ▼
                                      bilateral_flows  one agreed quantity per relation
brent/DCOILBRENTEU.csv           ──►  brent_annual     annual average oil price
distances/sea_distances_base.parquet  (used directly from raw, computed not downloaded)
```

| Table | Path | Grain (one row = …) | Written by |
|---|---|---|---|
| raw Comtrade | `data/raw/comtrade/{ISO3}_{year}.parquet` | one Comtrade record | `ptf.ingest.comtrade` |
| `trade_reports` | `data/clean/trade_reports.parquet` | one report: reporter, partner, flow, year | `ptf.clean.comtrade` + `ptf.clean.quality` |
| `mirror` | `data/clean/mirror.parquet` | one trade relation: year, exporter, importer | `ptf.clean.mirror` |
| `bilateral_flows` | `data/clean/bilateral_flows.parquet` | one trade relation: year, exporter, importer | `ptf.clean.reconcile` |
| `brent_annual` | `data/clean/brent_annual.parquet` | one year | `ptf.clean.brent` |
| `sea_distances` | `data/raw/distances/sea_distances_base.parquet` | one ordered pair of regions | `ptf.ingest.distances` |

Conventions: country codes are ISO 3166-1 alpha-3 (`DEU`); region codes come from
`config/regions.yaml` (`EUR`, `ROW`, …); `t` = metric tonnes; `USD` = current US dollars
(not inflation-adjusted); NaN / `<NA>` = unknown, never "zero".

The running example throughout is Saudi Arabia → Belgium, 2024.

---

## Raw: Comtrade records

The API records exactly as returned (47 columns) plus `fetched_at`. Only the columns used
downstream are listed; the others (descriptions, alternative quantities, legacy flags) are
mostly empty in the preview endpoint. Full field list: UN Comtrade API documentation.

| Column | Meaning | Unit | Example (BEL import from SAU, 2024) |
|---|---|---|---|
| `refYear` | reference year | year | 2024 |
| `reporterCode` | reporting country, numeric M49 code | – | 56 (Belgium) |
| `partnerCode` | partner country; 0 = World (all partners) | – | 682 (Saudi Arabia) |
| `flowCode` | `M` import, `X` export, `RM`/`RX` re-import/re-export | – | `M` |
| `cmdCode` | HS commodity code | – | `3901` |
| `partner2Code`, `customsCode`, `motCode` | breakdowns; we request totals only (`0`, `C00`, `0`) | – | 0, `C00`, 0 |
| `netWgt` | net weight | kg | 170,919,571 |
| `isNetWgtEstimated` | Comtrade estimated the weight itself | bool | False |
| `primaryValue` | trade value; CIF for imports, FOB for exports | USD | 190,189,511 |
| `fetched_at` | when we downloaded the record (added by us) | UTC timestamp | 2026-11-12 19:41 |

The preview API returns no ISO codes or names; `comtrade_reference/partnerAreas.parquet`
maps `PartnerCode` → `PartnerCodeIsoAlpha3` and marks aggregates (`isGroup`).

---

## `trade_reports`

One row per report. A shipment can appear twice: once as the exporter's export report,
once as the importer's import report.

| Column | Meaning | Unit / type | Origin | Example |
|---|---|---|---|---|
| `year` | reference year | int | `refYear` | 2024 |
| `month` | month; empty for annual data | Int64, `<NA>` | – | `<NA>` |
| `reporter_iso3` | country that filed the report | ISO3 | `reporterCode` via reference table | BEL |
| `partner_iso3` | trade partner as named by the reporter; `S19` is mapped to `TWN` | ISO3 or Comtrade pseudo code | `partnerCode` via reference table | SAU |
| `flow` | `import` or `export` (re-exports excluded) | str | `flowCode` | import |
| `hs_code` | commodity code | str | `cmdCode` | 3901 |
| `qty_t` | net weight; NaN if Comtrade gives 0 or nothing | t | `netWgt` / 1000 | 170,919.6 |
| `value_usd` | trade value (imports CIF, exports FOB) | USD | `primaryValue` | 190,189,511 |
| `source` | data source | str | constant | comtrade |
| `qty_estimated_by_source` | weight was estimated by Comtrade, not reported | bool | `isNetWgtEstimated` | False |
| `is_imputed` | quantity imputed by us; always False at this stage | bool | – | False |
| `imputation_method` | method if imputed; always empty at this stage | str / None | – | None |
| `unit_value_usd_t` | price per tonne; NaN without quantity or value | USD/t | `value_usd / qty_t` | 1,112.7 |
| `uv_robust_z` | distance of the log unit value from the median of its year and flow, in robust standard deviations | – | quality rule 1 | −0.79 |
| `is_uv_outlier` | `abs(uv_robust_z)` above the threshold in `config/pipeline.yaml` (3.0) | bool | quality rule 1 | False |

---

## `mirror`

Both reports of the same trade relation side by side. Suffix `_export` = from the exporter's
export report, `_import` = from the importer's import report. A side is empty when that
country did not report the relation or is not among our reporters.

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `year` | reference year | int | 2024 |
| `exporter_iso3` | exporting country | ISO3 | SAU |
| `importer_iso3` | importing country | ISO3 | BEL |
| `qty_t_export` | quantity according to the exporter | t | 479,541.6 |
| `value_usd_export` | value according to the exporter (FOB) | USD | 428,004,831 |
| `qty_estimated_by_source_export` | exporter's weight estimated by Comtrade | bool, empty if no report | False |
| `is_uv_outlier_export` | exporter's report has an outlier unit value | bool, empty if no report | False |
| `qty_t_import` | quantity according to the importer | t | 170,919.6 |
| `value_usd_import` | value according to the importer (CIF) | USD | 190,189,511 |
| `qty_estimated_by_source_import` | importer's weight estimated by Comtrade | bool, empty if no report | False |
| `is_uv_outlier_import` | importer's report has an outlier unit value | bool, empty if no report | False |
| `has_both_reports` | both sides reported a quantity | bool | True |
| `qty_gap_pct` | (import − export) / mean of both × 100; between −200 and +200; NaN unless both sides exist | % | −94.9 |
| `cif_fob_ratio` | `value_usd_import / value_usd_export`; around 1.1–1.3 when both sides agree on quantity | ratio | 0.44 |

How to read the example: Saudi Arabia reports almost three times the quantity that Belgium
records. Because the quantities disagree, the value ratio (0.44) is far from the usual
CIF/FOB markup too. Likely cause: goods landed in Antwerp but cleared by customs elsewhere
in the EU (see methodology, section 1.6).

---

## `bilateral_flows`

One agreed quantity per trade relation, chosen by the rule order in methodology section 1.4.
This is the table the model (phase 2) builds on.

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `year` | reference year | int | 2024 |
| `exporter_iso3` | exporting country | ISO3 | SAU |
| `importer_iso3` | importing country | ISO3 | BEL |
| `exporter_region` | model region of the exporter; unlisted countries → `ROW` | region code | MDE |
| `importer_region` | model region of the importer | region code | EUR |
| `qty_t` | agreed quantity | t | 170,919.6 |
| `value_usd` | value from the same report (CIF if `basis` is import, FOB if export) | USD | 190,189,511 |
| `basis` | which rule produced `qty_t`: `import_report`, `export_report`, `imputed_from_import`, `imputed_from_export` | str | import_report |
| `is_imputed` | quantity estimated by us (value ÷ regional unit value) | bool | False |
| `imputation_method` | `value_div_regional_unit_value` if imputed, else empty | str / None | – |
| `qty_estimated_by_source` | the chosen quantity is Comtrade's estimate; always False for our own imputations | bool | False |
| `qty_t_import` | importer's quantity, kept for traceability | t | 170,919.6 |
| `qty_t_export` | exporter's quantity, kept for traceability | t | 479,541.6 |
| `qty_gap_pct` | mirror gap, copied from `mirror` | % | −94.9 |

Imputed example: Austria → Mexico 2019. Mexico reports 3.0 m USD of imports from Austria
without a weight; Austria is not among our reporters. Quantity = 3,006,221 USD ÷ NAM median
import unit value ≈ 1,986 t, `basis = imputed_from_import`.

---

## `brent_annual`

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `year` | calendar year | int | 2024 |
| `brent_usd_per_bbl` | mean of daily Brent spot prices (FRED `DCOILBRENTEU`) | USD/barrel | 80.5 |
| `quoted_days` | number of trading days with a price; check this for the current, incomplete year | days | 254 |

---

## `sea_distances`

Base case (only the Northwest Passage blocked). Phase 3 computes scenario variants with
further passages blocked (e.g. Suez).

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `origin_region` | region the cargo leaves | region code | MDE |
| `dest_region` | region the cargo arrives in | region code | EUR |
| `origin_port` | representative port of the origin region (`config/regions.yaml`) | str | Jebel Ali |
| `dest_port` | representative port of the destination region | str | Rotterdam |
| `distance_nm` | shortest sea route according to `searoute`; 0 within a region | nautical miles | 6,262 |
