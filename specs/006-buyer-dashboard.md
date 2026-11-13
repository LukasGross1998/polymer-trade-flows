# 006 – Buyer dashboard: situation, prices and drivers, sourcing exposure

- **Status:** done
- **Branch / PR:** `feat/buyer-dashboard` / see PR
- **SPEC.md sections:** 7 (app), 10 (next steps); ADR-014

## Goal

The app answers the questions of a **polyethylene buyer in Europe** (e.g. a packaging
converter in Germany) instead of being organised by data source:

1. *Do I need to act today?* – a situation page with three traffic lights.
2. *Where is my raw-material price heading?* – feedstock and resin prices in EUR or USD.
3. *Whom do I depend on?* – where Europe's PE imports come from and **which share passes a
   chokepoint that is disrupted right now**.

The third point combines two data sets we already have (BACI trade flows, PortWatch
chokepoint status) into something neither shows alone. Existing tabs for chokepoints, ports
and the port network stay as the logistics detail.

## Acceptance criteria

1. **Tab order:** Situation · Prices & drivers · Sourcing · Chokepoints · Ports · Trade
   flows. "Situation" replaces "Overview", "Prices & drivers" replaces "Energy & freight".

2. **New market series** (FRED, no key) in `config/markets.yaml`:
   - `DEXUSEU` (US dollars per euro, daily) for the EUR conversion;
   - `PCU325211325211` (US PPI plastics material and resin manufacturing, monthly) as a
     broader resin index next to the thermoplastics index.
   They appear in `marts.mart_market_series` with metadata (dbt test: accepted series).

3. **Route passages:** the sea-distance table also stores which passages each region-to-region
   route traverses (`searoute`, `return_passages=True`). A mapping in `config/sourcing.yaml`
   links searoute passages to PortWatch chokepoints (`suez` → Suez Canal, `babalmandab` →
   Bab el-Mandeb, `ormuz` → Strait of Hormuz, `malacca`, `gibraltar`, `panama`, ...).
   Example: Middle East (Jebel Ali) → Europe (Rotterdam) passes Hormuz, Bab el-Mandeb, Suez,
   Gibraltar; North America (Houston) → Europe passes none of the mapped chokepoints.

4. **Import sources mart** `marts.mart_import_sources` (dbt): per year, importer region and
   exporter country: tonnes, value, exporter region, share of the importer region's
   **extra-regional** imports. dbt tests: key unique, shares between 0 and 1, shares of one
   year and importer region sum to 1.

5. **Chokepoint exposure** (`ptf.insights.exposure`): for the focus region (config: `EUR`)
   and the latest trade year, the share of extra-regional imports whose route passes at
   least one chokepoint that is flagged *disrupted* today (monitor metrics, all vessels).
   Test with hand-checkable numbers: imports MDE 40 t (Hormuz, Bab el-Mandeb, Suez) and NAM
   60 t (none); Bab el-Mandeb disrupted → exposure 40 %; nothing disrupted → 0 %.

6. **Sourcing tab:**
   - treemap of extra-regional imports by exporter country, coloured by region;
   - Sankey: exporter region → route (e.g. "Hormuz + Red Sea", "Atlantic, no chokepoint")
     → Europe; routes through a disrupted chokepoint highlighted;
   - KPIs: extra-regional imports (Mt), intra-European share, exposure share, top-3
     supplier countries' share (concentration);
   - a note that the data year is the latest BACI year (2024) and routes use one
     representative port per region.

7. **Prices & drivers tab:**
   - currency switch EUR / USD for USD-denominated series (conversion with `DEXUSEU` of the
     same day; monthly series with the monthly average rate);
   - feedstock and resin series indexed to 2019 = 100 in one chart (Brent, Henry Hub,
     European gas, both resin indices), so the buyer sees whether resin follows feedstock;
   - existing charts (oil, gas, freight proxy, FX, GSCPI) stay.
   Test: Brent 80 USD with 1.10 USD/EUR → 72.73 EUR.

8. **Situation tab:** three traffic lights with value, change and a sparkline (price and
   logistics; the supply light has no history to draw); thresholds in
   `config/sourcing.yaml` (`source: assumption`, documented in `docs/methodology.md`):
   - **Price:** change of Brent in EUR over 90 days – amber from +5 %, red from +10 %
     (rising prices are bad for a buyer);
   - **Supply:** chokepoint exposure (criterion 5) – amber from 10 %, red from 25 %;
   - **Logistics:** latest GSCPI – amber from 0.5, red from 1.0 standard deviations.
   Below: "what changed in the last 7 days" (new disruption events, chokepoints newly
   flagged, largest 30-day price moves). Tests per light with values on both sides of each
   threshold.

9. Quality gates as usual (ruff, mypy, import-linter, pytest ≥ 85 %, dbt tests, data
   dictionary for the new table and column).

## Out of scope

- Landed-cost calculator (spec 007) and Eurostat monthly imports (spec 008).
- Per-country export ports (e.g. Yanbu on the Red Sea instead of Jebel Ali for Saudi
  Arabia); the limitation is shown in the app and documented.
- Paid freight indices (Drewry WCI, SCFI); the FRED freight PPI stays the proxy.
- Alerts by e-mail, news signals (GDELT), weather (NOAA).
- Changing the LP or the monitor metrics.

## Design notes

- **New package `ptf.insights`** for logic that combines domains (exposure = trade × routes ×
  chokepoint status; traffic lights = markets × shipping). Domains must not import each
  other (ADR-012), and the app must not hold business logic. `insights` becomes a layer
  between the entry points and the domains: `cli | app` → `insights` → domains → `core`.
  The import-linter contract is extended; ADR-014 records it.
- **Route passages** belong to the model domain (it already computes routes with searoute);
  stored as a list column `passages` in `sea_distances_base.parquet`. The mapping to
  PortWatch chokepoints lives in `config/sourcing.yaml`, read by `insights`.
- **Known searoute quirk** (found while writing this spec): with Suez and Bab el-Mandeb
  blocked, Shanghai → Rotterdam routes via Panama, not the Cape. Irrelevant here (base routes
  only) but noted for the scenario work.
- **First numbers** (BACI 2024, real data): Europe imports 18.6 Mt, of which 11.8 Mt within
  Europe; of the 6.8 Mt from outside, the Middle East supplies 2.8 Mt and North America
  2.7 Mt. With Bab el-Mandeb disrupted, roughly 40 % of extra-European imports would be
  exposed – the headline the Sourcing tab is built around. Implemented result: 52 %,
  because the Asian routes (Malacca, Bab el-Mandeb, Suez) count as well.
- The drivers chart uses a log scale: European gas rose tenfold in 2022 and flattened every
  other line on a linear axis.
- UI labels stay English like the rest of the app.
- Files: `config/markets.yaml`, `config/sourcing.yaml` (new), `src/ptf/model/distances.py`,
  `src/ptf/insights/{config,exposure,signals}.py` (new),
  `dbt/models/marts/trade/mart_import_sources.sql` + YAML,
  `src/ptf/app/tabs/{situation,prices,sourcing}.py` (situation/prices replace
  overview/markets), `pyproject.toml` (import-linter), docs, CHANGELOG, SPEC.md §10
  (also: Airflow postponed, possibly hosted later).
