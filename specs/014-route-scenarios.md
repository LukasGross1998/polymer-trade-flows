# 014 – Route scenarios: availability vs. transit risk, one scenario for all tabs

- **Status:** draft
- **Branch / PR:** `feat/route-scenarios` / see PR
- **SPEC.md sections:** 5 (scenarios), 7 (app); revises the route switch of specs 007 and 010
  and the chokepoint details of spec 013

## Goal

All tabs tell the same story. A blocked chokepoint either costs time and money because a
detour exists (Bab el-Mandeb, Suez: around the Cape), or it removes supply because no sea
detour exists (Hormuz). The monitor's live status sets the default route scenario, and that
one scenario drives the situation page, sourcing, landed cost and the order planner. Routes
are assigned per country where the region's port is wrong for that country (Egypt, Israel,
Saudi Arabia, Uzbekistan).

## Acceptance criteria

1. **Two kinds of chokepoint risk** (`config/sourcing.yaml`, new block `chokepoints`). Each
   chokepoint on the import routes is either
   - *bypassable*: it names the route variant that avoids it (`detour: red_sea_closed` for
     Bab el-Mandeb and Suez, `detour: malacca_closed` for Malacca via Sunda/Lombok), so a
     closure adds sea days and freight; or
   - *not bypassable* (Hormuz, Bosporus, Gibraltar, Dover): a closure makes the volume
     behind it *at risk – availability uncertain*.
   Test: Hormuz has no detour; Bab el-Mandeb's detour is `red_sea_closed`.

2. **Chokepoint details on the situation page** use the chokepoint's own detour. Extra sea
   days are computed only for the tonnes whose route passes that chokepoint, with the variant
   that avoids it; a chokepoint without a detour shows "no sea detour – supply at risk"
   instead of extra days. Today's bug ("Hormuz … Red Sea closed: +14 days via the Cape",
   the same for Gibraltar) is gone. Test with hand numbers: region A (100 t) passes Hormuz and
   Bab el-Mandeb with 6,000 nm open and 10,032 nm closed; region B (100 t) passes only Bab
   el-Mandeb with 8,000 / 12,032 nm; at 14 kn → Bab el-Mandeb +12.0 days (4,032 nm / 336 nm
   per day), Hormuz: no detour.

3. **Route scenario** (new block `scenarios` in `config/sourcing.yaml`), four options:
   - **Live status** (default): a chokepoint counts as *closed* when its 7-day traffic is at
     least `closed_below_pct` (50 %) below normal; between the monitor's disrupted flag and
     that level it counts as *reduced* (lead-time buffer, see 5). Bypassable closed
     chokepoints switch the routes behind them to their detour variant.
   - **All routes open**: base distances, nothing closed.
   - **Red Sea closed**: Bab el-Mandeb and Suez closed → variant `red_sea_closed`.
   - **Hormuz closed**: Hormuz closed → Gulf origins at risk; routes unchanged.
   A scenario resolves to: the set of closed chokepoints, the set of reduced chokepoints and
   one distance table per origin. Tests: with deviations Hormuz −95 %, Bab el-Mandeb −58 %,
   Suez −30 % (disrupted flag from −30 %, `shipping.yaml`), live status gives closed = {Hormuz, Bab el-Mandeb},
   reduced = {Suez}, distances = `red_sea_closed`.

4. **Country routes** (`config/sourcing.yaml`, block `country_routes`). Where a country does
   not ship from its region's representative port, it gets its own port(s); sea distances
   and passages from these ports to the focus region are computed with searoute for the base
   case and every variant by `ptf model` (new raw file per variant, landing + dbt not needed:
   the app reads it like the region distances). Initial list (assumptions, marked for review):
   - EGY → Alexandria (Mediterranean, not Durban);
   - ISR → Haifa (Mediterranean, not Jebel Ali);
   - SAU → 50 % Al Jubail (Gulf, passes Hormuz) / 50 % Yanbu (Red Sea, passes Bab el-Mandeb or
     Suez only);
   - DZA, LBY, TUN, MAR → their Mediterranean port (instead of Durban);
   - UZB → see 6.
   A split country appears as one row per port ("Saudi Arabia via Yanbu", tonnes × share).
   Tests: Egypt's route to Rotterdam passes Gibraltar but not the Cape; the Saudi rows sum to
   the Saudi tonnes; under "Hormuz closed" only the Jubail half is at risk.

5. **Scenario drives landed cost and the order planner.**
   - Freight and sea days use the scenario's distance per origin.
   - An origin whose route passes a closed, not bypassable chokepoint is flagged `at_risk`:
     shown greyed with "availability uncertain", never `on_time`, never recommended.
   - A reduced chokepoint on the route adds `reduced_buffer_days` (assumption: 3).
   - "Suppliers in time" counts only origins that are on time and not at risk.
   Test: with Hormuz closed, a Qatar row arriving before "needed by" is at risk, not on time,
   not recommended, and not counted.

6. **Landlocked origins** (UZB): a country route can name an overland leg with
   `overland_days` and `overland_usd_t` to its export port (UZB: rail to Poti, Georgia,
   21 days, 120 USD/t – assumption) and `confidence: low`. Freight = overland + sea; the tab
   marks the row "low confidence". Test: UZB landed freight = 120 USD/t + sea freight from
   Poti.

7. **Supply light** splits the exposed share into *at risk* (behind a closed, not bypassable
   chokepoint) and *delayed* (behind a closed bypassable one, i.e. on a detour); the level
   still uses the sum, the card text shows both. Under "All routes open" the supply light is
   green.

8. **One scenario for all tabs:** a scenario dropdown in the page header (stored in a
   `dcc.Store`, kept when switching tabs) replaces the "Red Sea open/closed" radio items of
   landed cost and the order planner. Situation, sourcing, landed cost and the planner read
   it. The full global bar (grade, currency) follows in spec 016.

9. Quality gates as usual; methodology §6–10 updated (two risk kinds, scenario resolution,
   country routes); data dictionary for the new raw files; ADR-016 "route scenario from live
   status".

## Out of scope

- Partial closures in the LP or capacity-based reallocation (SPEC.md §5 scenarios).
- A Hormuz bypass by pipeline (Saudi East-West pipeline to Yanbu, UAE Habshan–Fujairah): it
  carries crude oil, not polyethylene; noted in the methodology.
- A full country-level routing of all exporters; only the listed exceptions.
- The global grade and currency bar, colours and tiles (spec 016).

## Design notes

- Today's data (14 Nov 2026, week 45): Hormuz −95 %, Bab el-Mandeb −58 %, Bosporus −56 %,
  Suez −30 %, Gibraltar +2 %, Malacca +18 %. Live status would thus close Hormuz, Bab
  el-Mandeb and Bosporus: Gulf origins at risk, Asian and Red Sea routes via the Cape.
  Bosporus closed puts a Black Sea route (UZB via Poti) at risk too; whether Black Sea origins
  matter at all for PE into Europe is small (Uzbekistan 151 kt).
- Root cause of the Hormuz bug: `insights.relevance.chokepoint_dependency` computes one
  detour delta per region (Middle East: +13 days) and gives it to every chokepoint on that
  region's route.
- New module `ptf.insights.scenario`: `Scenario` (name, closed, reduced, variant per origin),
  `resolve(name, status, config)`, `at_risk(chokepoint_ids, scenario)`. `view.landed_view` and
  `view.planner_view` take a `Scenario` instead of `red_sea_closed: bool`.
- `ptf.model.distances`: `build_country_distances(country_ports, focus_port, restrictions)`
  writes `data/raw/distances/country_distances_<variant>.parquet` (country, port, share,
  distance_nm, passages); `ptf.model` gets a `malacca_closed` variant (restrictions
  `[malacca]`, to be confirmed with searoute's passage list). Ports and coordinates live in
  `config/sourcing.yaml` (an insights assumption), but the computation stays in `model`, so
  `model/steps.py` reads them through `model.config` (no insights import, ADR-012).
- Files: `config/sourcing.yaml`, `config/model.yaml`, `src/ptf/insights/{config,scenario,
  exposure,relevance,landed_cost,planner,view}.py`, `src/ptf/model/{distances,steps,config}.py`,
  `src/ptf/app/{__main__,data}.py`, `src/ptf/app/tabs/{situation,sourcing,landed_cost,
  planner}.py`, tests, docs.
- Open questions for the user: the Saudi split (50/50), the reduced and closed thresholds
  (−30 % disrupted, −50 % closed), UZB via Poti vs. rail directly to Europe, rail cost 120 USD/t.
