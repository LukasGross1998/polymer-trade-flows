# 010 – Order planner: landed cost against arrival date

- **Status:** done
- **Branch / PR:** `feat/order-planner` / see PR
- **SPEC.md sections:** 7 (app), 10 (next steps); builds on specs 006, 007 and 009

## Goal

A buyer who needs polyethylene in Europe by a certain date sees, for every supplier
country, **what a tonne costs delivered and when it would arrive if ordered today**, and
which origin is the cheapest that still arrives in time. Route disruptions (Red Sea),
port congestion and storms on the route change both price and date.

## Acceptance criteria

1. **Lead time per origin** (`ptf.insights.planner`), in days:
   lead = origin port days + sea days + destination port days + buffers, where
   - sea days = sea distance (nm) / (speed (kn) × 24), with the distances of spec 007
     (Red Sea open or closed);
   - assumptions in `config/sourcing.yaml` (`source: assumption`): speed 14 knots (slow
     steaming of container ships), 4 days at the origin port (loading, export clearance),
     4 days at the destination (discharge, import clearance, to the warehouse);
   - congestion buffer (+3 days) if a monitored port of the origin or destination region is
     flagged below normal (port calls, monitor method);
   - weather buffer (+2 days) if a chokepoint on the route has a storm (red) forecast.
   Test: Middle East → Europe, 6,262 nm at 14 kn = 18.6 sea days + 4 + 4 = 26.6 days; with
   the Red Sea closed 11,045 nm = 32.9 + 8 = 40.9 days; with a congested destination port
   +3.

2. **Planner table** per supplier country (largest 10 by volume, grade filter as in spec
   008): landed cost EUR/t (spec 007), lead days, arrival date (= order date + lead days),
   on time yes/no against the need-by date, and flags (route through a disrupted chokepoint,
   storm on the route, congested port). Recommendation: the cheapest supplier that arrives
   on time; if none does, the earliest arrival. Test with hand numbers: three suppliers,
   need-by date that excludes the cheapest one → the second cheapest is recommended.

3. **Reference "buy in Europe":** price within Europe (spec 007 reference) with a short lead
   time (config: 7 days), so the buyer sees whether importing is worth the wait.

4. **New tab "Order planner"** (section Buying, after Landed cost):
   - inputs: need-by date (default: today + 45 days), quantity (t, default 500), grade,
     Red Sea open / closed;
   - scatter chart: x = arrival date, y = landed cost EUR/t, one point per origin (size =
     import volume), vertical line at the need-by date, the recommendation highlighted,
     late suppliers greyed out;
   - KPIs: recommended origin, its landed cost and arrival date, total cost for the
     quantity, saving or extra cost against buying in Europe;
   - table with all components and flags; a note that these are planning estimates (no
     real quotes, average transit times, one port per region).

5. Quality gates as usual; new assumptions in `config/sourcing.yaml` and
   `docs/methodology.md`.

## Open decision: daily price signal from Asia (not part of this spec until decided)

The only free near-real-time polyethylene price is the **LLDPE future on the Dalian
Commodity Exchange** (China, CNY/t). Two ways to get it, both need your OK:

- *A. Python library `akshare`* (Chinese open-source data library): convenient, but a large
  dependency with many transitive packages, and it scrapes public web endpoints (Sina
  Finance), which can change without notice. Installing it for a test was blocked by the
  permission check in this session.
- *B. Call the public quote endpoint directly with `requests`*: small, but the same
  unofficial endpoint; its terms of use need checking.
- *C. Skip* and rely on the monthly US index and the trade unit values.

If A or B is chosen, it becomes spec 011: daily DCE LLDPE price in USD and EUR on the
Prices tab and as an optional "indexed to today" basis for the landed cost.

## Out of scope

- Real price quotes or price-agency data (ICIS, Platts, Argus: paid licences).
- Live vessel ETAs from AIS (hosting phase, AISStream key exists).
- Inventory planning (safety stock, order quantities) and supplier capacities.
- Schedules of specific shipping lines; departure frequency (assumed: any day).

## Design notes

- Lead time combines model (distances), shipping (port status, weather) and the buyer
  config, so it lives in `ptf.insights.planner` (ADR-014).
- Sea days at 14 kn from our distances (real data, Red Sea open / closed): North America
  15.0 / 15.0, Middle East 18.6 / 32.9, India 18.9 / 32.2, Southeast Asia 24.9 / 35.3, China
  31.4 / 41.3, Northeast Asia 32.4 / 42.3 days. Shanghai–Rotterdam in reality takes about
  30–35 days via Suez, so the order of magnitude fits.
- The port buffer uses the ports in `config/shipping.yaml` mapped to regions by their
  country (e.g. Jubail, Jebel Ali → MDE; Rotterdam, Antwerp → EUR).
- Files: `config/sourcing.yaml`, `src/ptf/insights/{planner,view}.py`,
  `src/ptf/app/tabs/planner.py`, `src/ptf/app/__main__.py`, tests, docs.
- Implemented addition: overland days for landlocked exporters (`overland_days`, Uzbekistan
  +21) – without it Uzbekistan, routed from St. Petersburg, would arrive after 12 days.
- Open decision answered by the user: option A (AKShare) for the daily DCE price, spec 011.
