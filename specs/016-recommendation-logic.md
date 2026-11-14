# 016 – Recommendation logic: sourceable origins, confidence, price ranges, order timing

- **Status:** done
- **Branch / PR:** `feat/recommendation-logic` / see PR
- **SPEC.md sections:** 7 (app); builds on specs 007, 010, 014, 015 (ADR-016: only sourced
  values)

## Goal

The buying tabs recommend only origins a European buyer can actually use, say how much the
numbers can be trusted, and show ranges where the data give a range. The order planner adds
the latest order date and the number of containers; landed cost can carry the buyer's own
cost quotes. No estimate enters without a source (ADR-016): where a cost has no free
source, the buyer enters it, and the app shows it as the buyer's input.

## Acceptance criteria

1. **Sourceable filter** (`config/sourcing.yaml`, block `sourceable`):
   - an origin is *not sourceable* if TARIC lists an import control under EU sanctions for
     it (`import_controls`, today Iran: Reg. 267/2012; Russia: Reg. 833/2014), or if the user
     lists it under `sourceable.blocked` (setting, e.g. company policy);
   - an origin is *minor* below `sourceable.min_volume_t` tonnes of exports to Europe in the
     latest BACI year (setting, proposed 10,000 t);
   - not sourceable origins are greyed out with the reason ("EU import control: Reg.
     267/2012 – check the conditions in TARIC") and never recommended; minor origins are
     shown but marked;
   - the entries are marked `review: true` in the config until the user confirms them.
   Tests: Iran is not sourceable with the regulation as reason; an origin with 5,000 t is
   minor at a 10,000 t limit; a not sourceable origin is never recommended.

2. **Price range per origin** from the HS6 grades in BACI (`mart_import_sources_by_product`):
   - range = lowest to highest unit value among the grades with at least
     `price_range.min_grade_share` % of the country's tonnes (setting, proposed 10 %);
   - mix-adjusted price = the country's grade prices weighted with *Europe's* import mix of
     grades (the same basket for every origin), so differences between countries are not
     just product mix; the mix effect = unit value − mix-adjusted price;
   - landed cost shows "price (range)" instead of one number; with the grade filter set to
     one grade the range collapses to that grade's price.
   Test with hand numbers: grades A 100 t at 1,000 USD/t and B 300 t at 1,200 USD/t → range
   1,000–1,200, unit value 1,150; Europe's mix 50/50 → mix-adjusted 1,100, mix effect +50.

3. **Confidence per origin**: high / medium / low from three sourced inputs, each with a
   threshold that is a setting (`confidence` block):
   - volume: tonnes to Europe in the latest year (low below `min_volume_t`);
   - product-mix effect: |mix effect| in % of the unit value (medium from 5 %, low from 15 %);
   - data age: years between the BACI year and today (medium from 2, low from 3).
   The lowest of the three wins; the tooltip names the reason. Tests on both sides of each
   threshold.

4. **"vs. buying in Europe" as a range**, not a headline number: lowest to highest
   difference between the origin's price range and the European reference (intra-European
   unit value, also as grade range), labelled "excl. freight" while freight has no source,
   with "BACI {year}, annual unit values" as the basis. The big KPI tile shows the range.

5. **Order planner additions:**
   - *latest order date* per origin = need-by date − transit days − the buyer's own lead
     days; shown per row, "n/a" where the transit time is n/a;
   - the buyer's own lead days are inputs on the tab, default 0, labelled "your own
     estimate": production / booking before departure, customs clearance, delivery after
     arrival (no free source gives these per country, ADR-016);
   - *containers*: the quantity divided by the maximum payload of a 40-foot container from
     a sourced container specification → "at least N containers" (a box rarely carries its
     maximum, so this is a lower bound and labelled so).
   Tests: need-by 31 Dec, transit 15 days, own lead days 10 → latest order 6 Dec; 500 t at a
   maximum payload of 26.5 t → at least 19 containers.

6. **Landed cost components:**
   - *capital tied up in transit* = price × interest rate × transit days / 365, with a
     sourced euro interest rate series in the market pipeline (candidate: a euro-area
     3-month interbank or ECB rate via FRED, checked before use); n/a where transit days are
     n/a;
   - *insurance, port handling, on-carriage*: inputs for the buyer's own quotes (EUR/t or %
     of the price), default empty = not included, labelled "your quote";
   - the table shows each component in its own column and the sum; components that are n/a
     or not entered are named under the table ("not included: freight (no source),
     insurance (no quote)").
   Test: 1,000 EUR/t at 4 % for 30 days → 3.29 EUR/t.

7. Quality gates as usual; value register (new settings, the container payload and interest
   rate with source), methodology §13, CHANGELOG; ADR only if a new decision comes up.

## Out of scope

- Real freight rates (phase 5), monthly Comext prices instead of annual BACI (phase 5).
- Design of tiles, colours and the table with inline bars (phase 3 and 4); this spec adds
  columns and flags to the existing tables.
- Checking the conditions of the sanctions regulations in detail: the app shows the TARIC
  measure and leaves the legal check to the buyer.

## Design notes

- New `ptf.insights.sourceable` (filter, reasons) and `ptf.insights.confidence` (price
  range, mix adjustment, confidence); both take tables and config, no I/O.
- `insights.view.landed_view` adds columns price_low / price_high / mix_effect_pct /
  confidence / confidence_reason / sourceable / sourceable_reason / capital_eur_t and the
  user cost inputs; `planner.plan` adds latest_order and containers and excludes not
  sourceable origins from the recommendation.
- App: landed cost and planner get the user inputs (number fields) and the new columns;
  sourcing greys out not sourceable countries in the supplier chart.
- Sources to check during implementation and report before use: the 40-foot container's
  maximum payload (a carrier's or ISO container specification), the euro interest rate
  series (FRED / ECB), terms of use of both.
- Open questions for the user: the proposed settings (min volume 10,000 t, grade share
  10 %, confidence thresholds 5 / 15 % and 2 / 3 years); whether company-policy blocks
  are needed beyond the TARIC import controls.

## Implementation notes (14 Nov 2026)

- Sources checked: container payload from Hapag-Lloyd's 40' Standard page (28,750 kg max
  payload, 32,500 kg max gross; "values vary by manufacturer"), read in the browser because
  the page refuses automated fetches; the euro rate from FRED `IR3TIB01EZM156N` (OECD,
  monthly, newest value January 2026: 2.03 %). Both in the value register.
- Spec 016's example payload (26.5 t) is only the test's input; the config uses 28.75 t.
- The settings `sourceable` and `confidence` carry `review: true` until the user confirms
  them.
