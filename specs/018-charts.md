# 018 – Charts that answer the buyer's question

- **Status:** done
- **Branch / PR:** `feat/charts` / see PR
- **SPEC.md sections:** 7 (app); phase 4 of the user's dashboard plan (14 Nov 2026); builds
  on the theme of spec 017 and the sourced-values rule (ADR-016)

## Goal

Each chart answers one buying question at a glance: what is the situation, is the price
move feedstock or margin, where does my volume come from and through which routes, what
does each origin cost, and when must I order. Charts that need a closer look (index
comparisons, treemaps, scatter plots) are replaced by simpler forms. New conversion factors
need a source like every other value.

## Acceptance criteria

### Situation

1. **Summary sentence** above the cards, generated from the three lights and the scenario,
   e.g. "Supply critical: 16–39 % of extra-European PE imports are at risk behind Hormuz and
   12 % are on a detour; price OK; logistics elevated (live status, 15 Nov 2026)." Rules in
   code, wording tested for every level combination of supply.
2. **One list "Chokepoints and disruptions"** instead of two: per relevant chokepoint its
   traffic vs. normal, share of Europe's PE imports, detour or "at risk", and the open
   PortWatch events within the relevance radius under it. Events not near a chokepoint are
   listed once at the end.
3. **"What changed"** with thresholds in config (settings): weather only from the red
   (storm) level near relevant points, price moves only from `min_move_pct` (proposed 5 %),
   chokepoints only on a change of level. Each line gets one short note for the buyer
   ("Brent −29 % in 30 days → feedstock cost falls; resin prices usually follow with a
   lag"). The notes are fixed texts per kind of event and direction, not generated claims.
4. **Price card**: shows both the 30-day and the 90-day change; when they point in opposite
   directions by more than `divergence_pct` (setting, proposed 10 points), the card shows
   "Mixed" (watch level) instead of "OK".

### Prices & drivers

5. **Spread chart instead of the index chart:** Dalian LLDPE in USD/t minus Brent in USD/t
   (barrels per tonne of crude from a sourced conversion factor, e.g. the Energy Institute
   Statistical Review) – a "polymer over crude" spread; with the US resin price index on its
   own small chart below (index, not a price, so not subtracted). No spread is shown if the
   conversion factor has no source.
6. **Oil:** Brent only (WTI moves to the method panel as a note). **Gas:** the spread
   Europe − US as an area chart; the two series on request (legend toggle, hidden by
   default).
7. **Freight** gets its own chart (deep-sea freight PPI); **currencies** only EUR/USD;
   **GSCPI** as a small context chart (half width) next to freight.
8. **Dalian chart** titled "Asian price indicator: LLDPE futures, Dalian"; the trading-day
   note in plain words ("price of the trading day's close"), with the closing time taken from
   the exchange's published trading hours (to be sourced; without a source no time is
   shown).

### Sourcing

9. **Destinations in Europe:** the Sankey's right column splits Europe into destination
   groups (setting: country → group, proposed North-West Europe, Mediterranean, Turkey,
   Central & Eastern Europe, Other) from the importer country in `mart_bilateral_trade`.
   Test: Turkey 1.9 Mt in 2024 appears as its own destination.
10. **Supplier bar chart instead of the treemap:** one horizontal bar per supplier country,
    sorted by tonnes, coloured with the route encoding (open / detour / at risk / not
    sourceable), the smallest countries folded into "Other" (setting: top 15).

### Landed cost

11. **One table with inline bars** instead of chart + table: per origin a stacked bar of the
    cost components inside the row (price, duty, capital, your quotes; freight when
    sourced), the numbers next to it, confidence, route status; the "buy in Europe"
    reference as a line through the bar column.

### Order planner

12. **Timeline per origin instead of the scatter:** one row per origin from today (order)
    through "your days before departure" and the ship transit to the arrival and your days
    after it; the transit bar carries a range from the slowest to the fastest container
    ship size of the IMO table (sourced: 11.8–16.5 knots), the "needed by" date as a
    vertical line, the cost per tonne as the row label. Origins at risk or without transit
    time are listed below the chart, not drawn.
    Test: a 9,720 nm route gives 24.5 to 34.3 sea days (16.5 and 11.8 knots).

13. Quality gates as usual; README screenshots (left over from spec 017) updated; value
    register for the new settings and the crude conversion factor.

## Out of scope

- New data sources (phase 5: Comext, producer prices, freight indices, TTF, …).
- Forecasts.

## Design notes

- New pure functions in `ptf.insights` where there is logic (summary sentence, merged
  chokepoint list, change filtering, price divergence, destination groups, timeline rows);
  drawing in the tab modules with the theme of spec 017.
- Inline bars in the table: plain HTML divs with widths in % (no Plotly), coloured from the
  categorical palette in component order.
- Sources to check during implementation and report before use: barrels per tonne of crude
  oil (Energy Institute / IEA conversion tables).
- Settings to confirm: `min_move_pct` 5 %, `divergence_pct` 10 points, destination groups,
  top 15 suppliers.

## Implementation notes (16 Nov 2026)

- Sources: 7.32 barrels per tonne of crude (UN Energy Statistics Yearbook 2023, Table II);
  DCE day session closes at 15:00 Beijing time (Nanhua Futures trading-hours overview of
  18 Nov 2024). The old trading-hours text of spec 012 (CET times without a source) is gone.
- Buyer notes in "what changed" are fixed and neutral ("compare resin offers with it"), no
  forecasts.
- Destination groups only for all grades: `mart_bilateral_trade` has no grade split.
- Currencies: only EUR/USD is drawn; CNY and the dollar index stay in the pipeline (the CNY
  rate converts the Dalian price).
