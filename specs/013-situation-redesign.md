# 013 – Situation page for European PE buyers

- **Status:** done (user request 2026-11-14)
- **Branch / PR:** `feat/situation-redesign` / see PR
- **SPEC.md sections:** 7 (app); revises the Situation tab of spec 006

## Goal

The start page answers "do I need to act today?" for a polyethylene buyer in Europe without
noise: consistent time windows, only Europe-relevant regions by default, a direct
polyethylene price signal, graded traffic lights that make real exceptions stand out,
actions that lead to the right tab, and no developer text in the layout.

## Acceptance criteria

1. **7-day window:** "What changed in the last 7 days" shows price moves over 7 days,
   computed only for daily series (a monthly series has no 7-day change). Test: a daily
   series 100 → 110 within 7 days is listed as +10 %; a 30-day move is not.

2. **Europe relevance** (`config/sourcing.yaml`, `insights.relevance`), default view:
   - relevant supplier regions = the focus region plus regions with at least 5 % of its
     extra-regional imports (BACI 2024: Europe, Middle East, North America, Northeast Asia);
   - relevant chokepoints = those on the sea routes from these regions to Europe, plus
     configured extras on the approach to the ARA ports (Dover Strait);
   - relevant ports = configured ports in relevant regions;
   - relevant market series = a configured list (Brent, WTI, Henry Hub, EUR/USD, resin
     index, DCE LLDPE, …; not LNG Japan, not the CNY or dollar index).
   Weather warnings, chokepoints below normal, new events near irrelevant regions and
   price moves are filtered accordingly; a switch "Europe-relevant only / all" shows
   everything. Test: Tsugaru, Magellan and Ombai are not relevant; Hormuz, Bab el-Mandeb,
   Suez, Gibraltar, Malacca and Dover are.

3. **Graded traffic lights:** four levels green / yellow / orange / red with three
   thresholds per light (assumptions in config):
   - price (Brent in EUR, 90 days): yellow from +5 %, orange from +15 %, red from +30 %;
   - supply (exposure): yellow from 10 %, orange from 25 %, red from 50 %;
   - logistics (GSCPI): yellow from 0.5, orange from 1.0, red from 2.0 (peak 2021: 4.3).
   With today's data (price +27 %, exposure 52 %, GSCPI 1.26) this gives orange / red /
   orange instead of three times red. Tests on both sides of each threshold.

4. **Polyethylene card** (fourth card): Dalian LLDPE in EUR/t with its 7-day change and
   the latest quote (spec 011/012) when available, else the US resin price index with its
   monthly change; labelled as an indicator (no free European PE spot price exists). No
   traffic light of its own.

5. **Actions instead of "▲ Act":** each card has a context link that switches to the right
   tab: price → "Review drivers →" (Prices & drivers), supply → "Check routes →"
   (Sourcing), logistics → "View delays →" (Order planner), polyethylene → "See PE
   prices →" (Prices & drivers). The level stays visible as icon + word (OK / Watch /
   Elevated / Critical).

6. **Chokepoint details:** each entry in "Chokepoints furthest below normal" shows, as a
   tooltip and in a small second line, the share of Europe's extra-regional PE imports whose
   route passes it and, where a detour exists, the extra sea days via the Cape (Red Sea
   variant of spec 007, volume-weighted). Test with hand numbers.

7. **No developer text:** the footer with config paths is removed; the method notes move
   into an info icon (i) with a tooltip next to each card title and section heading.

8. **Data freshness in the header:** "Last updated: <date, time>" next to the "Update data"
   button (time of the last warehouse build), plus the latest data dates (chokepoints,
   markets); updated after "Update data".

9. Quality gates as usual; methodology updated.

## Out of scope / known gaps

- A real EU HDPE/LDPE spot price or a naphtha/ethylene spread: no free source (price
  agencies are paid; FRED has no naphtha); the Dalian price is the closest free indicator.
- "Commodity news": the dashboard has no news feed; the list shows events, weather and
  price moves only.
- Disruption events are filtered by their distance to relevant chokepoints and ports
  (within 1,000 km), since PortWatch events have coordinates but no route.
- Implemented results (14 Nov 2026): lights price OK (+3.5 %, Brent fell since the last
  check), supply critical (52 %), logistics elevated (1.26). Relevant for Europe: regions
  EUR, MDE, NAM, NEA; chokepoints Hormuz, Bab el-Mandeb, Suez, Gibraltar, Malacca, Dover.
  Malacca is relevant because Northeast Asia (8 %) ships through it.
