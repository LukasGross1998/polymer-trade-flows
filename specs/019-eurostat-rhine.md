# 019 – Monthly EU imports (Comext), EU resin price indices, Rhine water level at Kaub

- **Status:** draft
- **Branch / PR:** `feat/eurostat-sources` / see PR
- **SPEC.md sections:** 2 (data sources), 7 (app); phase 5 of the dashboard plan, the three
  sources that need no key and allow reuse (source check of 19 Nov 2026)

## Goal

The buyer sees this year's prices and volumes instead of BACI 2024, a European resin price
anchor, and whether the Rhine can carry full barges to the plants upstream. All three sources
are free, need no key and allow reuse: Eurostat (reuse with attribution, Decision
2011/833/EU) and PEGELONLINE (Datenlizenz Deutschland – Zero 2.0).

## Acceptance criteria

### Eurostat Comext (trade domain)

1. **Download** (`ptf ingest`, new module `ptf.trade.comext`): dataset DS-045409, monthly,
   reporter EU27_2020, flow import, all partners, the five PE grades (HS6 390110 … 390190),
   indicators value in EUR and quantity in 100 kg, from January of the year before last; one
   raw file per download, cached like the other sources (`max_age_days`). Partner ISO2 → ISO3
   via the existing country reference. Intra-EU partners are dropped.
   Test with a fake answer in the API's JSON-stat format.
2. **Warehouse:** landing file and dbt models `stg_comext__imports` and
   `marts.mart_eu_imports_monthly` (month, exporter_iso3, exporter_region, hs6, qty_t,
   value_eur, unit_value_eur_t) with dbt tests (keys, non-negative values, tonnes > 0 where a
   unit value is given); documented in the dbt YAML.
3. **Landed cost and sourcing**, new price basis "Comext, last 12 months" (default when
   available): per origin the import unit value of the last 12 complete months in EUR/t.
   Comext import values are CIF at the EU border (to be confirmed with Eurostat's
   methodology and cited): the unit value then already contains sea freight and insurance
   to the EU border, so the landed cost is CIF unit value + EU duty and "freight" shows
   "included (CIF)". Price ranges and confidence use the same 12 months per grade; data age
   becomes "months", so recent data no longer lowers the confidence. BACI stays as the basis
   for the region's full picture (UK, Turkey, Norway, Switzerland are not in Comext) and is
   labelled as such.
   Test with hand numbers: 1,000 t for 1.15 m EUR → 1,150 EUR/t CIF; with 6.5 % duty
   1,224.75 EUR/t landed.
4. **Sourcing tab:** a small chart of the EU's monthly extra-EU PE imports (thousand tonnes)
   by the five largest origins and "Other", last 24 months.

### Eurostat price indices (markets domain)

5. **Series** in the market pipeline (Eurostat API, no key): EU27 producer price index for
   plastics in primary forms (`sts_inpp_m`, NACE C20.16, 2021 = 100) and the German import
   price index for the same goods from outside the euro area (`sts_inpi_m`, CPA C20.16,
   non-euro area) – the EU27 import series has no values in the API (checked 19 Nov 2026).
   New group `eu_prices`; dbt accepted values extended.
6. **Polyethylene card** on the situation page and the prices tab: the EU producer price
   index with its change to the previous month as the European price anchor, next to the
   Dalian price; labelled "index (2021 = 100), not a price".

### Rhine water level at Kaub (shipping domain)

7. **Download** (`ptf portwatch` step, new module `ptf.shipping.rhine`): PEGELONLINE REST
   API, station KAUB, water level W, the last 31 days (the API keeps no more) plus the
   station's characteristic values; stored daily in the raw layer, so a longer history builds
   up from the first download on.
8. **Low-water flag from the source's own values:** the level is compared with the
   station's "GlW" (equivalent low water level, 77 cm at Kaub) and the WSV status
   (`stateMnwMhw`) – no thresholds of our own. Shown on the ports tab (chart of the stored
   history with GlW and mean water MW as lines) and in "what changed" when the status becomes
   "low".

9. Quality gates as usual; data dictionary, value register (no new world values except the
   cited CIF basis), methodology §15, README sources table, CHANGELOG.

## Out of scope

- US Census exports (needs a key the user has to create), Destatis (needs an account),
  freight indices, TTF and EUA (no free licence) – see the source check of 19 Nov 2026.
- A barge freight surcharge from the water level (no free source for the surcharge tables).

## Design notes

- Comext query (tested 19 Nov 2026): `.../comext/dissemination/statistics/1.0/data/DS-045409
  ?freq=M&reporter=EU27_2020&product=<hs6>&flow=1&indicators=VALUE_IN_EUROS&indicators=
  QUANTITY_IN_100KG&sinceTimePeriod=YYYY-MM` returns all 278 partners; data to September 2026
  on 19 Nov 2026.
- Kaub characteristic values (PEGELONLINE, 19 Nov 2026): GlW 77 cm, MW 208 cm (2010–2020),
  NW 25 cm, HSW 640 cm; current level 116 cm, status "normal".
- Files: `src/ptf/trade/{comext,steps,config}.py`, `src/ptf/markets/{eurostat,steps,config}.py`,
  `src/ptf/shipping/{rhine,steps,config}.py`, `config/{trade,markets,shipping}.yaml`,
  dbt staging + marts, `src/ptf/insights/{landed_cost,view,confidence}.py`, the tabs, tests,
  docs.
- Attribution in the method panels: "Source: Eurostat (DS-045409, sts_inpp_m, sts_inpi_m)"
  and "Source: PEGELONLINE, WSV, DL-DE Zero 2.0".
