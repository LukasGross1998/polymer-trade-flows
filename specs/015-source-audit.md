# 015 – Source audit: every number about the world has a source

- **Status:** done
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

## Research results (14 Nov 2026, criterion 3)

| Value | Finding | Source (read 14 Nov 2026) |
|---|---|---|
| Freight | Drewry WCI 12 Nov 2026: Shanghai–Rotterdam 3,504 USD/40ft, Shanghai–Genoa 4,168; other lanes only as an image; no Middle East or US Gulf lane. Terms: personal use allowed, no commercial use or redistribution without a licence. Tonnes per box: only the maximum payload of a 40ft box is documented, not a typical PE load → freight per tonne only as a lower bound. | drewry.co.uk WCI page and /terms |
| Ship speed | Fourth IMO GHG Study 2020 has speeds by ship size; the full PDF is 140 MB, not readable by the fetch tool. | imo.org |
| Port days | UNCTADstat US.PortCalls (bulk CSV, free): median time in port of container ships 2018–2023, only 22 economies (no Gulf state, no Egypt); measures the ship's time in port, not loading, clearance and delivery of cargo. World 2023: 0.71 days. | unctadstat-api.unctad.org/bulkdownload/US.PortCalls |
| LP capacity | McKinsey Global Institute, 30 Jun 2026 (data S&P Global): installed PE capacity 2025 China 42, North America 34, Middle East 23, Western Europe 14 Mt/yr; no other regions. Config values EUR 17 and CHN 38 contain unsourced adjustments. | mckinsey.com/mgi/our-research/polyethylene-widely-produced-but-not-one-size-fits-all |
| LP cost | Same page: levelized cost of a new 400 kt HDPE plant (incl. capex) Saudi Arabia 660, USA 690, China 1,135, Germany 1,305 USD/t – a greenfield cost, not the cash cost of existing plants the LP uses. No utilisation by region. | same |
| EU duty | TARIC, CN 3901 10 10 90, reference date 14 Nov 2026: third-country duty 6.50 %; preference 0 % for US (from 1 Jul 2026), KR (until 31 Dec 2026), EG, IL (from 16 May 2023), UZ (until 31 Dec 2026, not in the config yet); BR 5.20 % (1 May–31 Dec 2026); SA none. Import control for IR (R0267/12, from 30 Sep 2025) and RU (R0833/14, 19 Dec 2023–31 Dec 2027). | ec.europa.eu/taxation_customs/dds2/taric |
| Wave levels | WMO code table 3700: very rough 4–6 m, high 6–9 m (upper bound in the lower class). Matches amber 4 / red 6. | NOAA NCEI copy of WMO code 3700 |
| Port coordinates | UN/LOCODE pages refuse automated access (HTTP 403). | service.unece.org |
