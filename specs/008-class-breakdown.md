# 008 – Breakdown by class: commodities, vessels, polyethylene grades

- **Status:** done
- **Branch / PR:** `feat/class-breakdown` / see PR
- **SPEC.md sections:** 7 (app), 10 (next steps); builds on specs 006 and 007

## Goal

The app places polyethylene in the whole picture and splits every view into its classes,
from the top down:

1. **Commodity classes in world trade:** where PE sits next to fuels, ores, grains,
   chemicals and other plastics – by tonnes *and* by value.
2. **Vessel classes at chokepoints:** what actually passes Hormuz, Bab el-Mandeb or Suez
   (tankers, containers, dry bulk, ...) and which class dropped how much.
3. **Polyethylene grades:** Sourcing and Landed cost per grade (LDPE/LLDPE, HDPE, EVA,
   ...), so that prices of the same grade are compared.

The tabs are grouped into two sections, "Buying" and "Markets & logistics".

## Acceptance criteria

1. **Commodity classes** in `dbt/seeds/commodity_classes.csv` (HS prefix → class, parent
   class, display order), e.g. `27` Mineral fuels, `26` Ores, `10`/`12` Cereals and oilseeds,
   `29` Organic chemicals, `3902`–`3914` Other plastics in primary forms, `3901`
   Polyethylene (parent: Plastics in primary forms), everything else "Other goods". The
   longest matching prefix wins. dbt test: every HS6 code of the trade data gets exactly one
   class.

2. **Landing of the whole BACI file:** `ptf clean` also writes
   `baci/landing_all_hs4.parquet` – world trade per year and HS4 heading (value, tonnes),
   streamed year by year from the zip (about 2 s per year, 11 million rows each). Only the
   aggregate is stored, not the 2.9 GB of rows.

3. **Mart `marts.mart_trade_by_class`** (dbt): per year and class: value (USD), tonnes,
   share of value and share of tonnes in world trade; with the parent class for the
   drill-down. dbt tests: key unique, shares between 0 and 1, shares of a year sum to 1.
   Check on real data (BACI 2024): mineral fuels 42.6 % of tonnes and 13.2 % of value;
   polyethylene 0.5 % of tonnes and 0.4 % of value. Test with the fixture zip (it already
   holds a crude-oil flow next to the PE flows).

4. **New tab "World trade by class"** (section "Markets & logistics"):
   - side-by-side bars: share of tonnes vs. share of value per class (latest year), so the
     "fuels dominate tonnes, finished goods dominate value" effect is visible;
   - a treemap drill-down: all goods → plastics in primary forms → polyethylene →
     the five PE grades (tonnes);
   - development of the classes over the years (tonnes, indexed 2019 = 100);
   - a note that BACI covers all transport modes, not only sea (most bulk tonnage moves by
     sea, but the shares are not "seaborne shares").

5. **Vessel classes at chokepoints** (`ptf.shipping.metrics`):
   - composition of traffic per chokepoint by vessel class (container, tanker, dry bulk,
     general cargo, RoRo) as share of transits, and by capacity where PortWatch gives it
     (container, tanker, rest);
   - per class: the latest 7-day mean against the seasonal normal (the existing baseline
     method applied per vessel type).
   Shown in the Chokepoints tab: a stacked bar "composition now vs. normal" for the selected
   chokepoint and a small table "change by vessel class". Check on real data: Strait of
   Hormuz 2025 – tankers 70 % of capacity (822 of 1,175 million t). Test with hand numbers.

6. **PE grade filter** in Sourcing and Landed cost (dropdown: all grades, or one of the five
   HS6 grades). New mart `marts.mart_import_sources_by_product` (year, importer region,
   exporter country, HS6: tonnes, value); the insights functions receive the filtered and
   summed rows, so exposure and landed cost work unchanged per grade. Test: with only HDPE
   selected, the exposure and the unit price are computed from HDPE rows alone.

7. **Navigation:** two sections as top-level tabs, each with its sub-tabs:
   - *Buying:* Situation · Prices & drivers · Sourcing · Landed cost
   - *Markets & logistics:* World trade by class · Chokepoints · Ports · Trade flows
   Component ids stay unchanged, so existing callbacks and tests keep working.

8. Quality gates as usual; new tables in dbt YAML and the data dictionary; class definitions
   documented in `docs/methodology.md`.

## Out of scope

- Seaborne trade by cargo type from UNCTAD (crude, products and gas, dry bulk,
  containers): UNCTADstat has a data centre, but no documented API was found. Checked
  during implementation; if a stable download exists, it becomes spec 009, otherwise a small
  reference table with source in a later spec.
- Commodity classes by importer region (e.g. Europe's imports by class): only world
  totals here, to keep the landing small.
- Eurostat monthly imports (moves to spec 010).
- Python classes / refactoring of the code structure (not meant by "classes" here).

## Design notes

- Commodity classes are a trade concern: the landing lives in `ptf.trade.baci`, the class
  mapping as a dbt seed, the mart in `dbt/models/marts/trade/`. Vessel classes are a
  shipping concern (`ptf.shipping.metrics`, vocabulary already has the five vessel types).
  The grade filter touches `insights` and the two buyer tabs only.
- Grades come from `dim_product` (390110 LDPE/LLDPE, 390120 HDPE, 390130 EVA, 390140
  ethylene-alpha-olefin copolymers, 390190 other).
- First numbers (BACI 2024, all modes): mineral fuels 6.3 bn t / 3.0 tn USD; ores 2.1 bn t;
  cereals and oilseeds 0.7 bn t; organic chemicals 243 Mt; other plastics in primary forms
  129 Mt; polyethylene 70 Mt / 86 bn USD.
- Files: `dbt/seeds/commodity_classes.csv`, `dbt/models/staging/trade/stg_baci__all_hs4.sql`,
  `dbt/models/marts/trade/mart_trade_by_class.sql`, `mart_import_sources_by_product.sql`,
  `src/ptf/trade/baci.py`, `src/ptf/shipping/metrics.py`, `src/ptf/insights/view.py`,
  `src/ptf/app/__main__.py` (sections), `src/ptf/app/tabs/{classes,chokepoints,sourcing,landed_cost}.py`,
  tests, docs.
- Implemented: the drill-down treemap starts at "Plastics in primary forms" instead of
  all goods – plastics are 1.4 % of world tonnes, too small to click in a treemap of all
  goods; the bar chart shows the world context.
