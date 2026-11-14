# 009 – Marine weather, official EU duties, nautical chart layer

- **Status:** done
- **Branch / PR:** `feat/weather-duties-seamap` / see PR
- **SPEC.md sections:** 7 (app), 10 (next steps); builds on specs 006–008

## Goal

Three free sources that need no key, each closing a gap:

1. **Marine weather** (Open-Meteo): storms are a cause of delays the dashboard does not
   show yet – today it sees conflicts and traffic, not weather. Wave height and wind gusts at
   every chokepoint and monitored port, the past 7 days and a 7-day forecast, with storm
   warnings.
2. **Official EU duties** (World Bank WITS, TRAINS): the third-country duty in the landed
   cost comes from an unchecked TARIC mirror; WITS gives the EU's MFN rate per HS6 grade
   (checked by hand: 390110 → 6.5 % in 2022).
3. **Nautical chart layer** (OpenSeaMap): seamarks and harbours as a switchable layer on the
   chokepoint and port maps.

## Acceptance criteria

1. **Weather download** (`ptf.shipping.weather`): one request per variable group for all
   locations at once (Open-Meteo accepts lists of coordinates):
   - marine API: daily `wave_height_max` (m);
   - forecast API: daily `wind_gusts_10m_max`, `wind_speed_10m_max` (km/h);
   - `past_days=7`, `forecast_days=7`; locations = the 28 PortWatch chokepoints
     (`dim_chokepoint`) and the configured ports (`dim_port`).
   Raw layer: one Parquet per download in `data/raw/weather/`, never overwritten. Points on
   land have no wave data (null) – kept as null, not 0. Runs as part of `ptf portwatch`
   (daily shipping refresh) and of the app's "Update data". Test with a fake session
   (two locations, hand-written JSON).

2. **Weather marts** (dbt, tag `shipping`): `stg_openmeteo__weather` (latest download wins
   per location and day, like PortWatch) and `marts.mart_marine_weather` (date, location id,
   location type chokepoint/port, name, wave height, gusts, wind, `is_forecast`). dbt tests:
   key unique, values ≥ 0, location type accepted values.

3. **Storm warnings** (`config/shipping.yaml`, `source:` Beaufort scale / assumption):
   amber from waves ≥ 4 m or gusts ≥ 62 km/h (Beaufort 8, gale), red from waves ≥ 6 m or
   gusts ≥ 89 km/h (Beaufort 10, storm). Function `storm_level` and a list of locations with
   a warning in the next 7 days. Tests on both sides of each threshold.

4. **App:**
   - Chokepoints and Ports tabs: a weather card for the selected location – wave height and
     gusts as two small charts (no dual axis), past 7 days solid, forecast dashed, threshold
     lines, plus "next storm warning: <date>" or "no warning in the next 7 days";
   - Situation tab, "what changed": storm warnings in the forecast for chokepoints and ports
     ("Storm forecast at Strait of Hormuz on 16 Nov: gusts 95 km/h").

5. **EU duties from WITS** (`ptf.trade.duties`): MFN rate of the EU (WITS reporter 918,
   partner 000 = world) per PE grade (the five HS6 codes), latest year available (tries the
   last five years). Raw XML per download in `data/raw/wits/`; parsed to a landing file;
   `marts.mart_eu_duty` (hs6, year, mfn_pct, source). Test: parse a saved response snippet →
   6.5. Runs in `ptf ingest`.

6. **Landed cost uses WITS:** the third-country rate per grade comes from `mart_eu_duty`
   (for "all grades": import-weighted average of the grade rates); preferential rates stay
   in `config/sourcing.yaml`; `default_pct` remains the fallback when WITS has no rate. The
   tab says which source a rate comes from. Test: grade with WITS rate 6.5 and a preference
   of 0 for the USA → USA 0, Saudi Arabia 6.5.

7. **Nautical chart layer:** the chokepoint and port maps switch from a plain world map
   (`Scattergeo`) to a tile map (`Scattermap`, MapLibre) with a light base map and a
   switchable OpenSeaMap seamark layer (`tiles.openseamap.org/seamark/{z}/{x}/{y}.png`).
   Markers, colours and click-to-select stay as they are. The trade-flow network map keeps
   its world map (lines between ports).

8. **API keys documented:** `.env.example` lists every key the project knows, empty, with
   what it is for: `COMTRADE_API_KEY` (legacy), `AISSTREAM_API_KEY` (live AIS, hosting phase,
   not used yet), `EIA_API_KEY` (not used yet); README section "Data sources and keys" with
   a table: source, key needed, used for, status.

9. Quality gates as usual; new tables in dbt YAML and the data dictionary; thresholds and
   sources in `config/` and `docs/methodology.md`.

## Out of scope

- Live vessel positions (AISStream; key exists in `.env`, but it needs a permanently running
  worker – hosting phase), EIA data (needs a key the user does not have yet).
- Weather along whole routes (only at the chokepoints and ports); ocean currents; tropical
  cyclone tracks.
- Preferential duty rates from WITS (WITS returns only MFN for the EU in a quick test).
- Map tiles on the trade-flow network map.

## Design notes

- Weather belongs to the shipping domain (locations are PortWatch chokepoints and ports);
  duties to the trade domain; the duty lookup in landed cost stays in `insights`.
- Open-Meteo: free for non-commercial use without key, fair-use limits; two requests per
  refresh are well within them. Checked: Bab el-Mandeb 13 Nov 2026 – waves up to 0.8 m,
  gusts up to 49 km/h.
- WITS answers in SDMX XML (`OBS_VALUE`, `TARIFFTYPE="MFN"`); parsed with the standard
  library (`xml.etree`), no new dependency.
- OpenSeaMap tiles are loaded by the browser, not by our code; the base map (Carto
  Positron or OpenStreetMap) as well. Without internet the maps show markers only.
- Files: `config/shipping.yaml`, `src/ptf/shipping/{weather,steps}.py`,
  `src/ptf/trade/{duties,steps}.py`, `dbt/models/staging/shipping/stg_openmeteo__weather.sql`,
  `dbt/models/marts/shipping/mart_marine_weather.sql`, `dbt/models/marts/trade/mart_eu_duty.sql`,
  `src/ptf/insights/{landed_cost,view}.py`, `src/ptf/app/charts.py` (tile map),
  `src/ptf/app/tabs/{chokepoints,ports,situation,landed_cost}.py`, `.env.example`, README,
  tests, docs.
- Implemented results: WITS 2023 – 6.5 % highest line for all five grades (HDPE and other
  ethylene polymers have a second line at 0 %, average 3.25 %), so the landed cost uses the
  highest line. Weather for 39 locations; on 14 Nov 2026 a storm forecast at the Tsugaru
  Strait (gusts 122 km/h) and gale-force gusts at Rotterdam and Houston. The seamark switch
  also zooms to the selected location, because seamarks only show from about zoom 8.
