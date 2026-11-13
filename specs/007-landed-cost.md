# 007 – Landed cost by supplier country

- **Status:** done
- **Branch / PR:** `feat/landed-cost` / see PR
- **SPEC.md sections:** 7 (app), 10 (next steps); builds on spec 006

## Goal

A buyer in Europe sees **what one tonne of polyethylene costs delivered to Europe from each
supplier country**, broken into price, sea freight and EU duty, in EUR, and how that ranking
changes when the Red Sea is closed or freight rates rise. The cheapest origin on paper is not
always the cheapest delivered.

## Acceptance criteria

1. **Formula** (`ptf.insights.landed_cost`), per exporter country, in USD/t then EUR/t:
   - `price` = BACI unit value of the country's exports to Europe (value / tonnes, FOB),
     latest year; optionally scaled to today with the resin price index (criterion 4);
   - `freight` = (fixed + variable per 1,000 nm × distance) × freight factor, with the
     existing freight assumption of the LP (`config/model.yaml`: 40 USD/t + 7 USD/t per
     1,000 nm) and the sea distance from the exporter's region to Europe;
   - `duty` = duty rate × (price + freight) (EU customs value is CIF; insurance ignored);
   - `landed` = price + freight + duty, converted with the latest `DEXUSEU`.
   Test: price 1,000 USD/t, 6,000 nm, factor 1, duty 6.5 %, 1.10 USD/EUR →
   freight 82, duty 70.33, landed 1,152.33 USD/t = 1,047.57 EUR/t; factor 2 → freight 164,
   duty 75.66, landed 1,239.66 USD/t.

2. **Red Sea closed:** a second distance table with Suez and Bab el-Mandeb blocked
   (`sea_distances_red_sea_closed.parquet`, restrictions in `config/model.yaml`). Panama is
   blocked too, because searoute otherwise sends Asian cargo through Panama instead of
   around the Cape (found in spec 006). Expected: Jebel Ali → Rotterdam 6,262 nm → about
   11,045 nm around the Cape; Houston → Rotterdam unchanged. Test on the route table.

3. **Duty rates** in `config/sourcing.yaml`: default (third-country) rate 6.5 % and
   per-country preferential rates, each with `source:`. Starting values (read on a TARIC
   mirror, 2026-11-13, to be checked in the official EU TARIC before relying on them):
   USA 0 % (from 2026-07-01), South Korea 0 %, Egypt 0 %, Israel 0 %, Mercosur 5.2 %;
   others (Saudi Arabia, Qatar, UAE, Kuwait, China, ...) the default 6.5 %.

4. **Price basis switch:** "BACI unit value (2024)" or "indexed to today" = unit value ×
   (resin index latest / resin index average of the BACI year), with the US PPI plastics
   resin index (`PCU325211325211`). Test: index average 300 in the base year, 330 now →
   prices × 1.10. The tab says clearly that this is a proxy, not a quote.

5. **Landed cost tab** (new tab after Sourcing):
   - controls: route (Red Sea open / closed), freight factor (slider 0.5–3.0, default 1.0),
     price basis;
   - horizontal stacked bars (price, freight, duty) in EUR/t for the 10 largest supplier
     countries, sorted by landed cost, with the average price of trade within Europe as a
     reference line ("buy in Europe");
   - KPIs: cheapest origin, its gap to the European reference, and how much the Red Sea
     closure adds for the Middle East (EUR/t);
   - a table with all components and the volume (kt) per country.

6. Quality gates as usual; new assumptions in `config/` and `docs/methodology.md`; the
   route variant table in the data dictionary.

## Out of scope

- Real price quotes or contract prices (no free source); inland freight inside Europe;
  insurance, port fees, anti-dumping or safeguard duties; currency hedging.
- Country-specific export ports (still one port per region, as in spec 006).
- Scenario engine for the LP (later spec); only the distance variant is added here.
- Eurostat monthly imports (spec 008).

## Design notes

- `ptf.insights.landed_cost` combines trade (unit values from `mart_import_sources`),
  model (distances, freight assumption) and markets (FX, resin index) – an insight by the
  ADR-014 rule. Pure functions; the tab only draws.
- `ptf.model.distances` gets `ingest_route_variants`; `ptf ingest` writes the base table and
  the variant(s) from `config/model.yaml` (`route_variants: {red_sea_closed: [...]}`), so the
  later scenario work reuses them.
- First numbers (BACI 2024 unit values, FOB USD/t): USA 1,264, Saudi Arabia 1,186, Korea
  1,420, Qatar 1,114, Iran 1,026; average within Europe 1,512. With the US now duty-free and
  the Gulf at 6.5 %, the ranking is closer than the FOB prices suggest; with the Red Sea
  closed, Gulf freight rises from ~84 to ~117 USD/t (factor 1).
- Unit values are annual averages over all PE grades (LDPE, HDPE, LLDPE mix differs by
  country), so country differences partly reflect the product mix. Shown as a caveat.
- Files: `config/model.yaml`, `config/sourcing.yaml`, `src/ptf/model/distances.py`,
  `src/ptf/model/steps.py`, `src/ptf/insights/landed_cost.py` (new),
  `src/ptf/app/tabs/landed_cost.py` (new), `src/ptf/app/data.py`, tests, docs.
- Implemented result (BACI 2024, 1.115 USD/EUR, factor 1): Uzbekistan 961 EUR/t,
  Iran 1,060, Qatar 1,144, USA 1,201, Saudi Arabia 1,213; European average 1,355 EUR/t; Red
  Sea closure +32 EUR/t for the Middle East. Found while checking: the model region Europe
  includes non-EU countries (UK, Turkey, ...), where EU duties do not apply – shown as a
  caveat in the tab and the methodology.
