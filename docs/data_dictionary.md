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

model (data/model/{year}/): region-level inputs and results of the transport LP
  observed_region_flows, region_balance, route_costs  ->  LP  ->  lp_flows, lp_regions
```

| Table | Path | Grain (one row = …) | Written by |
|---|---|---|---|
| raw Comtrade | `data/raw/comtrade/{ISO3}_{year}.parquet` | one Comtrade record | `ptf.ingest.comtrade` |
| `trade_reports` | `data/clean/trade_reports.parquet` | one report: reporter, partner, flow, year | `ptf.clean.comtrade` + `ptf.clean.quality` |
| `mirror` | `data/clean/mirror.parquet` | one trade relation: year, exporter, importer | `ptf.clean.mirror` |
| `bilateral_flows` | `data/clean/bilateral_flows.parquet` | one trade relation: year, exporter, importer | `ptf.clean.reconcile` |
| `brent_annual` | `data/clean/brent_annual.parquet` | one year | `ptf.clean.brent` |
| `sea_distances` | `data/raw/distances/sea_distances_base.parquet` | one ordered pair of regions | `ptf.ingest.distances` |
| `chokepoint_transits` | `data/clean/chokepoint_transits.parquet` | one chokepoint and day | `ptf.clean.portwatch` |
| `chokepoints` | `data/clean/chokepoints.parquet` | one chokepoint | `ptf.clean.portwatch` |
| `port_activity` | `data/clean/port_activity.parquet` | one port and day | `ptf.clean.portwatch` |
| `ports` | `data/clean/ports.parquet` | one configured port | `ptf.clean.portwatch` |
| `events` | `data/clean/events.parquet` | one disruption event | `ptf.clean.portwatch` |
| `market_series` | `data/clean/market_series.parquet` | one series and date | `ptf.clean.market` |
| `port_links` | `data/clean/port_links.parquet` | one directed port-to-port link | `ptf.clean.portwatch` |
| `country_trade` | `data/clean/country_trade.parquet` (optional) | one country and day | `ptf.clean.portwatch` |
| `observed_region_flows` | `data/model/{year}/observed_region_flows.parquet` | one region pair (incl. within a region) | `ptf.model.inputs` |
| `region_balance` | `data/model/{year}/region_balance.parquet` | one model region | `ptf.model.inputs` |
| `route_costs` | `data/model/{year}/route_costs.parquet` | one ordered pair of model regions | `ptf.model.inputs` |
| `lp_flows` | `data/model/{year}/lp_flows.parquet` | one ordered pair of model regions | `ptf.model.transport` |
| `lp_regions` | `data/model/{year}/lp_regions.parquet` | one model region | `ptf.model.transport` |

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

---

## `chokepoint_transits`

Daily vessel transits from IMF PortWatch (raw downloads in
`data/raw/portwatch/chokepoints_daily/`, one file per download). Example: Suez Canal,
2026-11-03.

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `date` | day of the transits | date | 2026-11-03 |
| `chokepoint_id` | PortWatch id | str | chokepoint1 |
| `chokepoint` | name | str | Suez Canal |
| `n_total` | all vessels | vessels/day | 39 |
| `n_container` | container ships | vessels/day | 12 |
| `n_tanker` | tankers | vessels/day | 16 |
| `n_dry_bulk` | dry bulk carriers | vessels/day | 8 |
| `n_general_cargo` | general cargo ships | vessels/day | 2 |
| `n_roro` | roll-on/roll-off ships | vessels/day | 1 |
| `n_cargo` | all cargo ships except tankers | vessels/day | 23 |
| `capacity` | deadweight tonnage of all transits | t/day | 1,918,291 |
| `capacity_container` | deadweight tonnage of container ships | t/day | 716,075 |
| `capacity_tanker` | deadweight tonnage of tankers | t/day | 924,628 |
| `fetched_at` | when this value was downloaded; the latest download per day is kept | UTC timestamp | 2026-11-12 20:18 |

## `chokepoints`

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `chokepoint_id` | PortWatch id | str | chokepoint1 |
| `chokepoint` | name | str | Suez Canal |
| `lat` | latitude | degrees | 30.59 |
| `lon` | longitude | degrees | 32.44 |

## `port_activity`

Daily activity of the ports configured in `config/monitor.yaml` (IMF PortWatch
`Daily_Ports_Data`; raw downloads in `data/raw/portwatch/ports_daily/`). Example: Jubail,
2026-11-06.

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `date` | day | date | 2026-11-06 |
| `port_id` | PortWatch id | str | port24 |
| `port` | short name from the config | str | Jubail |
| `portcalls` | port calls, all vessels | vessels/day | 1 |
| `portcalls_tanker` | port calls of tankers | vessels/day | 1 |
| `portcalls_container` | port calls of container ships | vessels/day | 0 |
| `import` | estimated import volume (PortWatch estimate from draught and capacity) | t/day | 536 |
| `export` | estimated export volume | t/day | 62,716 |
| `fetched_at` | when this value was downloaded; the latest download per day is kept | UTC timestamp | 2026-11-12 20:34 |

## `ports`

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `port_id` | PortWatch id | str | port24 |
| `port` | short name from the config | str | Jubail |
| `country` | country | str | Saudi Arabia |
| `lat` | latitude | degrees | 27.06 |
| `lon` | longitude | degrees | 49.66 |

## `events`

PortWatch disruption events (`portwatch_disruptions_database`, newest download).

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `event_id` | PortWatch id | int | (id) |
| `event_type` | DR drought, EQ earthquake, FL flood, OT other (e.g. conflict), TC tropical cyclone, VO volcano, WF wildfire | str | OT |
| `event` | name | str | HORMUZ-26 |
| `alert_level` | GREEN, ORANGE or RED | str | RED |
| `country` | affected country, if any | str | – |
| `from_date` | start | date | 2026-03-01 |
| `to_date` | end; empty while ongoing | date | – |
| `lat` | latitude | degrees | 26.30 |
| `lon` | longitude | degrees | 56.86 |
| `affected_ports` | PortWatch ids of affected ports or chokepoints | str | chokepoint6 |
| `n_affected_ports` | number of affected ports | int | 1 |
| `description` | short text | str | Trade Disruptions in the Strait of Hormuz from: 01 Mar 2026 |

## `market_series`

All market series in one long table: FRED series from `config/market_data.yaml` and the NY
Fed GSCPI (raw downloads in `data/raw/fred/{id}/` and `data/raw/gscpi/`).

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `date` | observation date (monthly series: first day of the month; GSCPI: last day) | date | 2026-11-03 |
| `series_id` | FRED id, or `GSCPI` | str | DCOILBRENTEU |
| `name` | readable name | str | Brent crude oil |
| `unit` | unit of `value` | str | USD/bbl |
| `frequency` | daily or monthly | str | daily |
| `group` | energy, gas, freight_polymers, fx, supply_chain | str | energy |
| `value` | observation | see `unit` | 107.03 |

## `port_links`

Port-to-port shipping network (PortWatch `spillovers_port_level_impact`, a static snapshot
last updated May 2025). Only links with at least `min_link_capacity` (1,000 t) of daily
capacity: 8,084 of ~227,000 links, ~71 % of the total capacity. All vessel types together.
Example: Port Hedland → Tianjin, the largest long-haul link (iron ore).

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `from_port_id` | PortWatch id of the origin port | str | port955 |
| `from_port` | origin port | str | Port Hedland |
| `from_country` | origin country | str | Australia |
| `from_lat` | latitude of the origin | degrees | −20.33 |
| `from_lon` | longitude of the origin | degrees | 118.56 |
| `to_port_id` | PortWatch id of the destination port | str | port1297 |
| `to_port` | destination port | str | Tianjin Xin Gang |
| `to_country` | destination country | str | China |
| `to_lat` | latitude of the destination | degrees | 38.94 |
| `to_lon` | longitude of the destination | degrees | 117.73 |
| `transit_days` | average voyage time | days | 18.5 |
| `daily_capacity` | vessel capacity (deadweight tonnes) travelling on the link per day; PortWatch's "daily capacity at risk"; not the cargo carried | t/day | 125,444 |

## `country_trade`

Optional (`download_country_trade` in `config/monitor.yaml`, off by default: the first
download takes 20–25 minutes). Daily estimated imports and exports per country by vessel
type (PortWatch `Daily_Trade_Data_REG`, from vessel draught and capacity).

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `date` | day | date | 2026-11-06 |
| `iso3` | country code | ISO3 | SAU |
| `country` | country name | str | Saudi Arabia |
| `import` | estimated imports, all vessel types | t/day | 38,716 |
| `export` | estimated exports, all vessel types | t/day | 64,036 |
| `import_tanker` | imports by tankers (oil, products, chemicals, LNG/LPG) | t/day | – |
| `import_dry_bulk` | imports by dry bulk carriers (ore, coal, grain) | t/day | – |
| `import_container` | imports by container ships | t/day | – |
| `import_general_cargo` | imports by general cargo ships | t/day | – |
| `import_roro` | imports by RoRo ships (vehicles) | t/day | – |
| `export_tanker` | exports by tankers | t/day | 62,716 |
| `export_dry_bulk` | exports by dry bulk carriers | t/day | 0 |
| `export_container` | exports by container ships | t/day | 273 |
| `export_general_cargo` | exports by general cargo ships | t/day | – |
| `export_roro` | exports by RoRo ships | t/day | – |
| `fetched_at` | when this value was downloaded; the latest download per day is kept | UTC timestamp | – |

---

# Model layer (`data/model/{year}/`)

Inputs and results of the transport LP for the base year in `config/model.yaml`.
Model regions only; `ROW` is not part of the LP. Examples: base year 2023, Middle East and
Europe.

## `observed_region_flows`

`bilateral_flows` of one year summed by region pair.

| Column | Meaning | Unit / type | Example |
|---|---|---|---|
| `exporter_region` | region of the exporting countries | region code | MDE |
| `importer_region` | region of the importing countries | region code | EUR |
| `qty_t` | agreed quantity, summed over all country pairs | t | 2,087,406 |

## `region_balance`

| Column | Meaning | Unit / type | Example (EUR) |
|---|---|---|---|
| `region` | model region | region code | EUR |
| `capacity_t` | nameplate PE capacity (assumption, `config/model.yaml`) | t/year | 17,000,000 |
| `production_t` | assumed production = capacity × utilisation | t/year | 12,750,000 |
| `imports_t` | observed imports from other regions (incl. `ROW`) | t/year | 5,241,361 |
| `exports_t` | observed exports to other regions (incl. `ROW`) | t/year | 1,367,695 |
| `net_imports_t` | `imports_t − exports_t` | t/year | 3,873,666 |
| `demand_t` | apparent consumption = production + net imports; the LP must cover it | t/year | 16,623,666 |

## `route_costs`

| Column | Meaning | Unit / type | Example (MDE → EUR) |
|---|---|---|---|
| `origin_region` | supplying region | region code | MDE |
| `dest_region` | receiving region | region code | EUR |
| `origin_port` | representative port of the origin | str | Jebel Ali |
| `dest_port` | representative port of the destination | str | Rotterdam |
| `distance_nm` | sea distance (from `sea_distances`) | nautical miles | 6,262 |
| `prod_cost_usd_t` | cash cost of production in the origin (assumption) | USD/t | 500 |
| `freight_usd_t` | fixed + variable × distance; 0 within a region | USD/t | 83.8 |
| `tariff_usd_t` | tariff on this route; 0 in the base case | USD/t | 0 |
| `unit_cost_usd_t` | delivered cost = production + freight + tariff | USD/t | 583.8 |

## `lp_flows`

| Column | Meaning | Unit / type | Example (MDE → EUR) |
|---|---|---|---|
| `origin_region` | supplying region | region code | MDE |
| `dest_region` | receiving region; equal to origin = local supply | region code | EUR |
| `qty_t` | optimal shipment `x_ij` | t/year | 2,780,158 |
| `unit_cost_usd_t` | delivered cost used by the LP | USD/t | 583.8 |

## `lp_regions`

| Column | Meaning | Unit / type | Example (MDE) |
|---|---|---|---|
| `region` | model region | region code | MDE |
| `capacity_t` | capacity limit used in the LP | t/year | 23,000,000 |
| `supply_t` | total optimal shipments from this region | t/year | 23,000,000 |
| `demand_t` | demand the LP had to cover | t/year | 12,711,230 |
| `unmet_t` | demand left uncovered (`u_j`), priced at the penalty | t/year | 0 |
| `prod_cost_usd_t` | cash cost of production (assumption) | USD/t | 500 |
| `price_usd_t` | dual of the demand constraint: implied regional price | USD/t | 1,017.8 |
| `rent_usd_t` | magnitude of the capacity dual: scarcity rent; 0 with idle capacity | USD/t | 517.8 |
| `utilisation` | `supply_t / capacity_t` in the optimum | share 0–1 | 1.0 |

In the example, price = production cost + rent (500 + 518): the Middle East runs at full
capacity and earns the gap to the marginal supplier.
