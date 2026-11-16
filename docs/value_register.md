# Value register (spec 015)

Rule (user, 14 Nov 2026): the dashboard shows only values confirmed by a data source, with no
exceptions. Every number in `config/*.yaml` is listed here:

- **sourced**: a fact about the world. In the config it is written as
  `{value, source, url, read}` (`ptf.core.sourced.Sourced`, or `SourcedTable` for a table of
  values from one source). A fact without source, url and read date does not load.
- **setting**: a choice of the user, not a claim about the world (thresholds, years,
  technical limits). Plain numbers in the config.
- **removed**: a former value without a source. The views that used it show "n/a".

`tests/test_value_register.py` checks that every number in the config files is listed here
with the right class, and that every listed key still exists. `*` matches one key level,
`[]` any list item. Data downloaded by the pipeline (BACI, PortWatch, FRED, WITS, …) carries
its source in `docs/data_dictionary.md` and is not repeated here.

## Sourced

| File | Key | Value | Source (read) |
|---|---|---|---|
| model.yaml | `regions.*.capacity_mt` | NAM 34, EUR 14, MDE 23, CHN 42 Mt/yr | McKinsey Global Institute, "Polyethylene: Widely produced – but not one-size-fits-all" (30 Jun 2026; data S&P Global), installed capacity 2025 (14 Nov 2026). EUR = Western Europe only. |
| markets.yaml | `dce.day_close_hour` | 15 (Beijing time) | Nanhua Futures, trading hours overview of 18 Nov 2024: DCE LLDPE day session 9:00–10:15, 10:30–11:30, 13:30–15:00 (16 Nov 2026) |
| markets.yaml | `crude_barrels_per_tonne` | 7.32 bbl/t | UN Energy Statistics Yearbook 2023, Table II, conventional crude oil of average specific gravity (16 Nov 2026) |
| model.yaml | `country_routes.*` | export ports of EGY (Alexandria), ISR (Haifa), SAU (Al Jubail, Yanbu) | EGY: Oil & Gas Journal on SIDPEC's Alexandria complex; ISR: Global Energy Monitor, Carmel Olefins at Haifa Bay; SAU: SABIC manufacturing affiliates (Kemya, Sharq at Al Jubail; Yansab, Yanpet at Yanbu) (14 Nov 2026). Port coordinates inside an entry are a setting (a point in the port). Shares per port are not published. |
| sourcing.yaml | `landed_cost.duty.default_pct` | 6.5 % | EU TARIC, third-country duty, CN 3901 10 10 90 (14 Nov 2026). Fallback; the rate per grade comes from World Bank WITS in the pipeline. |
| sourcing.yaml | `landed_cost.duty.preferential.*` | 0 % USA, CAN, MEX, KOR, JPN, SGP, EGY, ISR, DZA, ZAF, UZB; 5.2 % BRA, ARG, URY, PRY | EU TARIC tariff preferences with validity dates, CN 3901 10 10 90 (USA also 3901 20 90 00) (14 Nov 2026). |
| sourcing.yaml | `lead_time.speed_knots` | 11.8–16.5 kn by ship size | Fourth IMO GHG Study 2020, Table 35: average speed over ground at sea, container ships by TEU size, 2018 (14 Nov 2026). |
| sourcing.yaml | `lead_time.container_payload_t` | 28.75 t | Hapag-Lloyd, 40' Standard container: max payload 28,750 kg; values vary by manufacturer (14 Nov 2026). Used as a lower bound for the number of containers (spec 016). |
| sourcing.yaml | `lead_time.port_days` | 0.30–1.56 days, 22 economies | UNCTADstat US.PortCalls, median time in port of container ships, 2023 (bulk file of March 2024) (14 Nov 2026). Ship's time in port, not cargo handling. |

## Settings

| File | Key | Value | Why it is a setting |
|---|---|---|---|
| comtrade.yaml | `comtrade.years[]` | 2019–2024 | years to download (legacy check) |
| comtrade.yaml | `comtrade.request_pause_seconds` | 1.5 | API politeness |
| comtrade.yaml | `comtrade.max_retries` | 5 | technical |
| comtrade.yaml | `cleaning.outlier_mad_threshold` | 3.0 | statistical cut-off chosen by the user |
| markets.yaml | `max_age_days` | 1 | download cache age |
| model.yaml | `base_year` | 2023 | year the LP is compared with |
| model.yaml | `penalty_usd_t` | 5000 | technical LP cost of unmet demand |
| regions.yaml | `regions.*.port.lon`, `regions.*.port.lat` | one point per region | the representative port of a region is a modelling choice; searoute snaps the point to the nearest sea lane |
| shipping.yaml | `baseline_years[]` | 2019–2023 | years that define "normal" traffic |
| shipping.yaml | `rolling_window_days` | 7 | smoothing window |
| shipping.yaml | `disruption_threshold` | 0.7 | "disrupted" below 70 % of normal |
| shipping.yaml | `min_baseline_per_day` | 2.0 | ignore chokepoints with almost no traffic |
| shipping.yaml | `revision_days` | 14 | re-download window for revised data |
| shipping.yaml | `min_link_capacity` | 1000 | download filter |
| shipping.yaml | `weather.past_days`, `weather.forecast_days` | 7, 7 | display window |
| shipping.yaml | `weather.waves_m.amber`, `weather.waves_m.red` | 4.0, 6.0 m | which class counts as amber/red; boundaries from WMO code table 3700 ("very rough" from 4 m, "high" from 6 m) |
| shipping.yaml | `weather.gusts_kmh.amber`, `weather.gusts_kmh.red` | 63.0, 88.9 km/h | which class counts as amber/red; boundaries from the Met Office Beaufort scale (gale from 34 kn, storm from 48 kn; 1 kn = 1.852 km/h) |
| sourcing.yaml | `signals.price.days` | 90 | comparison window of the price light |
| sourcing.yaml | `signals.price.short_days` | 30 | second period on the price card (spec 018) |
| sourcing.yaml | `signals.price.divergence_pct` | 10 points | opposite 30- and 90-day moves at least this far apart show "Mixed" |
| sourcing.yaml | `top_suppliers` | 15 | supplier countries shown before "Other" (spec 018) |
| sourcing.yaml | `changes.min_move_pct` | 5 % | market moves listed in "what changed" |
| sourcing.yaml | `signals.*.yellow`, `signals.*.orange`, `signals.*.red` | see config | traffic-light thresholds |
| sourcing.yaml | `relevance.min_region_share` | 5 % | relevance limit |
| sourcing.yaml | `relevance.event_radius_km` | 1000 | relevance limit |
| sourcing.yaml | `recent_days` | 7 | "what changed" window |
| sourcing.yaml | `landed_cost.top_n` | 10 | number of suppliers shown |
| sourcing.yaml | `sourceable.min_volume_t` | 10,000 t | below this an origin is "minor" and has low confidence (spec 016, `review: true`) |
| sourcing.yaml | `price_range.min_grade_share` | 10 % | grades with at least this share of a country's tonnes span its price range |
| sourcing.yaml | `confidence.mix_medium_pct`, `confidence.mix_low_pct` | 5, 15 % | product-mix effect for medium / low confidence (`review: true`) |
| sourcing.yaml | `confidence.age_medium_years`, `confidence.age_low_years` | 2, 3 years | data age for medium / low confidence (`review: true`) |
| sourcing.yaml | `scenarios.closed_below_pct` | 50 % | live status: a chokepoint counts as closed when its 7-day traffic is at least this far below normal |
| sourcing.yaml | `lead_time.default_need_by_days` | 45 | planner default |
| sourcing.yaml | `lead_time.default_quantity_t` | 500 | planner default |
| trade.yaml | `baci.years[]` | 2019–2024 | years to download |
| trade.yaml | `wits.years_back` | 6 | how far back to look for a WITS rate |

## Removed (no source found, 14 Nov 2026)

| File | Former key | Former value | Reason / what the app shows |
|---|---|---|---|
| model.yaml | `freight.fixed_usd_t`, `freight.variable_usd_t_per_1000nm` | 40 USD/t, 7 USD/t per 1,000 nm | no free rate per tonne for all routes (Drewry WCI: Shanghai lanes only, no redistribution; tonnes per box not documented). Landed cost = price + duty, "freight n/a"; no planner recommendation. |
| model.yaml | `regions.*.utilisation` | 0.75–0.90 | no source. LP off. |
| model.yaml | `regions.*.prod_cost_usd_t` | 500–1,200 USD/t | no source for the cash cost of existing plants (McKinsey gives the levelized cost of a new plant). LP off. |
| model.yaml | `regions.{SAM,CIS,AFR,IND,NEA,SEA}.capacity_mt` | 3–11 Mt/yr | not in the McKinsey table. LP off. |
| sourcing.yaml | `lead_time.origin_port_days`, `lead_time.destination_port_days` | 4, 4 days | replaced by UNCTAD ship time in port; cargo handling has no source. |
| sourcing.yaml | `lead_time.congestion_buffer_days`, `lead_time.storm_buffer_days` | 3, 2 days | no source; congestion and storms are flags without days. |
| sourcing.yaml | `lead_time.europe_days` | 7 days | no source; "buy in Europe" has a price but no arrival date. |
| sourcing.yaml | `lead_time.overland_days.UZB` | 21 days | no source; Uzbekistan has no transit time (no UNCTAD port data either). |
| sourcing.yaml | `lead_time.speed_knots` (single value) | 14 kn | replaced by the IMO table. |
