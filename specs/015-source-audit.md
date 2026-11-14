# 015 – Source audit: every number about the world has a source

- **Status:** draft
- **Branch / PR:** `feat/route-scenarios` (implemented before spec 014) / see PR
- **SPEC.md sections:** 2 (data sources), 4 (LP parameters), 7 (app); touches specs 007 and 010

## Goal

The dashboard shows only values confirmed by a data source (user rule, 14 Nov 2026, no
exceptions). Every number in `config/` and in UI texts is either a sourced fact with its
source and date, or a user setting. Values without a source are removed, and the views that
used them show "n/a" with the reason instead of an estimate.

## Definitions

- **Sourced value:** a fact about the world (a cost, a duration, a capacity, a rate, a port)
  with `source` (publisher and document or dataset), `url` and `read` (date). A value derived
  from sourced values by a documented formula counts as sourced.
- **Setting:** a choice of the user, not a claim about the world: traffic-light thresholds,
  the monitor's disruption threshold, relevance limits, default quantity and need-by days,
  baseline years, the region grouping and each region's representative port, technical model
  parameters (LP penalty). Marked `setting` in the config; shown as "setting" in the
  methodology.
- **Unsourced:** neither. Removed.

## Acceptance criteria

1. **Value register** `docs/value_register.md`: one row per number in `config/*.yaml` and
   per number in UI texts and docs that states a fact (e.g. "Cape, 14 knots"): file and key,
   value, class (sourced / setting / derived / removed), source with URL and date, or the
   reason for removal. The register is complete: a test collects all numeric leaves of the
   YAML files and fails if one is missing from the register.

2. **Config schema:** sourced values are written as
   `{value: …, source: …, url: …, read: YYYY-MM-DD}`; settings live under keys named in the
   register as settings. Loading a config with a non-setting number without `source`, `url`
   and `read` fails (test). The free-text `source: assumption` disappears from all configs.

3. **Research the open values** below. For each candidate, first check access and terms of
   use, then report to the user before using it. Each value is either sourced with date, or
   removed:

   | Value today | Used for | Candidate sources to check |
   |---|---|---|
   | freight 40 USD/t + 7 USD/t per 1,000 nm | landed cost, LP | published container index lanes (Drewry WCI, Freightos FBX) with a sourced payload per box |
   | speed 14 kn | sea days | published carrier transit times per lane instead of distance ÷ speed |
   | port days 4 + 4 | lead time | UNCTADstat time in port per country |
   | congestion buffer 3 d, storm buffer 2 d | lead time | none known → expected: removed, flag only |
   | "buy in Europe" 7 days | planner reference | none known → expected: removed |
   | LP utilisation and production cost per region | flows tab (LP) | none free known → expected: removed |
   | LP capacity of SAM, CIS, AFR, IND, NEA, SEA; China "reduced for 2023" | LP | the McKinsey source of the other regions, if it covers them |
   | wave-height storm levels | weather warnings | Douglas sea scale (WMO code table 3700) |
   | EU duty rates (TARIC mirror) | landed cost | official TARIC consultation (`read` date) |

4. **Degraded views instead of estimates:**
   - landed cost without a sourced freight value: price + duty only, column "freight: n/a
     (no sourced rate)", no ranking claim "cheapest delivered";
   - order planner without sourced sea days or port days: arrival "n/a" with the missing
     component named; no "on time" flag, no recommendation;
   - congestion and storm stay as flags on the row ("port congestion", "storm on route"),
     without added days, unless a source gives days;
   - transport LP: switched off by `model.enabled: false` while capacities or costs are
     missing; the flows tab then shows the sourced trade flows and a note "model inputs not
     sourced"; `ptf model` skips the LP and still writes the distances.
   Tests per case with fake tables.

5. **UI texts:** numbers in hard-coded texts come from the config (e.g. the "Cape, 14 knots"
   tooltip on the situation page) or are removed. Test: no tab module contains a numeric
   literal inside a user-facing string except formatting (checked by a list of allowed
   patterns).

6. **Docs:** methodology sections that cite removed values are rewritten; README and
   `CLAUDE.md` rule "Wenn Daten fehlen oder nur als Annahme vorliegen" updated to "only
   sourced values; missing → n/a"; ADR-016 "Only sourced values"; CHANGELOG.

7. Quality gates as usual.

## Out of scope

- New time-series sources (Comext, freight indices, TTF, …): phase 5. This spec only uses
  static, dated values from documents.
- Spec 014 (route scenarios): implemented after this spec, on its results.
- Visual design of "n/a" states (design spec, phase 3).

## Design notes

- Order of work: register and schema first (criteria 1–2, mechanical), then the research
  report per value (criterion 3) for the user's OK, then the degraded views (4).
- New `ptf.core.sourced`: pydantic model `Sourced[T]` (`value`, `source`, `url`, `read`) used
  by the domain configs; `float(cfg.freight.fixed_usd_t.value)` in the code.
- A static dated value goes stale: the app shows the `read` date next to values derived from
  it (e.g. "freight per WCI, 12 Nov 2026").
- Files: `config/*.yaml`, `src/ptf/core/sourced.py`, the domain `config.py` files,
  `src/ptf/insights/{landed_cost,planner,view}.py`, `src/ptf/model/steps.py`,
  `src/ptf/app/tabs/{situation,landed_cost,planner,flows}.py`, `docs/value_register.md`,
  `docs/methodology.md`, `docs/decisions.md`, `CLAUDE.md`, tests.
- Expected result if little can be sourced: landed cost shows price and duty, the planner
  shows routes and flags without dates, the LP is off. That is the intended behaviour of the
  rule, not a failure; phase 5 sources (freight indices) can fill the gaps later.
