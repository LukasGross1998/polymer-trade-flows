# Methodology

Model assumptions, data treatment and known limitations. Every number that is an assumption
lives in `config/` and is explained here. Generated figures and tables: [data_quality.md](data_quality.md). Every table and column:
[data_dictionary.md](data_dictionary.md).

## 1. Data & cleaning

### 1.1 Scope

| Item | Choice | Where |
|---|---|---|
| Product | HS 3901, polyethylene in primary forms, split into five HS6 products (LDPE/LLDPE 390110, HDPE 390120, EVA 390130, ethylene-alpha-olefin copolymers 390140, other 390190) | `config/trade.yaml` |
| Years | 2019–2024, annual | `config/trade.yaml` |
| Countries | all ~200 countries in BACI, mapped to 10 regions (section 2) | `config/regions.yaml` |

### 1.2 Sources

| Source | What | Access | Raw layer |
|---|---|---|---|
| **CEPII BACI** (V202601, HS 2017) | reconciled bilateral trade per HS6 product: value (thousand USD, FOB) and quantity (t) | one ~800 MB zip, free, Etalab 2.0 (ADR-009) | `data/raw/baci/BACI_HS17_V202601.zip`, kept unchanged |
| searoute | sea distance between representative ports | Python package, offline | `data/raw/distances/` |
| FRED `DCOILBRENTEU` | Brent spot price, daily, USD/bbl | CSV download, no key (ADR-004) | `data/raw/fred/DCOILBRENTEU/` |
| UN Comtrade (check only) | our own download of annual reports, phase 1 | public preview API (ADR-003) | `data/raw/comtrade/` |

Raw files are never overwritten.

### 1.3 BACI -> warehouse (dbt)

BACI is built by CEPII from UN Comtrade: for every flow it combines the exporter's and the
importer's report, removes estimated freight and insurance from import values (so values are
FOB) and weights each country's reports by their reliability, judged by how far they deviate
from the partners' reports. This is what we did ourselves in phase 1 (section 1.4), for all
countries and with a more elaborate weighting.

Since ADR-011 the transformations are SQL models in dbt (`dbt/models`), built into
`data/warehouse.duckdb`:

- **Python** unpacks the zip: the yearly CSVs are read in chunks and HS 3901xx is kept,
  values unchanged (`landing_hs3901.parquet`), plus BACI's country and product lists;
  `config/regions.yaml` is written as reference tables
- **staging** (`stg_*`): types and base units (value × 1,000 → USD); "Other Asia, nes"
  (`S19`) → `TWN` via the aliases in the configuration
- **marts**, a star schema: dimensions `dim_country`, `dim_region`, `dim_product`; fact
  `fct_trade` (year × exporter × importer × HS6); `mart_bilateral_trade` and
  `mart_region_trade` for analysis and the LP
- missing quantities (445 product flows, < 0.1 % of tonnage) are imputed in `fct_trade` as
  value ÷ median unit value of the same HS6 product and year (a window median in SQL) and
  flagged (`is_imputed`)
- 34 dbt tests check keys, relationships to the dimensions, non-negative values and that
  every country has exactly one region; `dbt build` fails if one does not hold
- the move from pandas was checked for parity: all 34,341 relations and 92,947 product flows
  identical, largest difference 5 × 10⁻¹⁰ t (floating-point noise)

### 1.4 Own Comtrade reconciliation (phase 1, superseded, kept as a check)

Phase 1 downloaded Comtrade reports directly and reconciled them ourselves. The public
endpoint's daily quota stopped the download at 17 of 30 reporters (ADR-003, ADR-009). The
rules below are kept in the code (`ptf comtrade`) and the result is compared with BACI
in the data-quality report.

#### Comtrade raw -> clean

`trade_reports` (one row per report, schema in SPEC section 3):

- keep flows `M` (import) and `X` (export); re-exports/re-imports are excluded
- keep totals only (`partner2Code=0`, `customsCode=C00`, `motCode=0`)
- drop the partner "World" and other aggregate areas
- numeric area codes -> ISO3 via the Comtrade reference table; "Other Asia, nes" (`S19`) is
  Comtrade's convention for **Taiwan** and is mapped to `TWN`
- net weight kg -> tonnes; a weight of 0 or missing becomes NaN ("unknown", not "zero")
- `qty_estimated_by_source` keeps Comtrade's own flag `isNetWgtEstimated`: Comtrade
  already fills missing weights itself, and we do not want to hide that

#### Quality rules

**Rule 1 – unit values and outliers.** `unit_value_usd_t = value_usd / qty_t`. A report is an
outlier if its log unit value is more than `outlier_mad_threshold` (3.0) robust standard
deviations away from the median of its year and flow. The robust standard deviation is the
MAD (median absolute deviation) × 1.4826. Median and MAD are not distorted by the outliers
themselves; the log makes "10× too high" and "10× too low" equally far away. Imports (CIF) and
exports (FOB) are grouped separately. Typical causes: a wrong weight (unit error), or tiny lots
(samples, specialty grades) with very high prices. On the first real data (7 American
reporters) about 9 % of reports were flagged, but only 0.05 % of the tonnage: the median
flagged lot was 0.4 t. The report therefore shows outliers by count and by tonnage.

**Rule 2 – mirror statistics.** Every trade relation can be reported twice: by the exporter
(export to B) and by the importer (import from A). `mirror` puts both side by side per
(year, exporter, importer) and measures the quantity gap symmetrically:

    qty_gap_pct = (qty_import − qty_export) / mean(qty_import, qty_export) × 100

The gap is measured on **quantities**, because import values contain freight and insurance
(CIF) while export values do not (FOB). The CIF/FOB value ratio is reported separately; a
median slightly above 1 is expected.

Reasons why the two sides differ: CIF vs. FOB valuation, timing (shipped in December,
arrived in January), country of origin vs. country of consignment (goods routed via Belgium
or Singapore), misclassification, confidential trade and countries that do not report at all.

**Rule 3 – reconciliation (`bilateral_flows`).** One agreed quantity per relation, first
matching rule wins:

1. import report with a plausible unit value
2. export report with a plausible unit value
3. import report with an outlier unit value
4. export report with an outlier unit value
5. import value ÷ regional median import unit value (imputed)
6. export value ÷ regional median export unit value (imputed)

Imports are preferred because customs authorities control imports more closely (duties are
levied on them). Rules 1–2 extend the SPEC slightly: an implausible import report loses to a
plausible export report. The regional unit value is the median of non-outlier reports of the
reporting country's region in that year and flow, with the global median as fallback.

**Rule 4 – flagging.** Imputed rows have `is_imputed=True` and
`imputation_method="value_div_regional_unit_value"`; `basis` says which rule was used.

**Rule 5 – report.** `uv run ptf report` writes
[data_quality.md](data_quality.md) and `docs/figures/dq_*.png`: coverage per reporter and
year, mirror gaps, source of the agreed quantity, outliers and an inter-regional trade matrix.

### 1.5 Known limitations

- BACI is published once a year; the latest data year is 2024. Recent months are covered
  only by the PortWatch-based monitor (sections 4 and 5).
- HS 3901 contains EVA and other ethylene polymers besides PE grades; the HS6 split in
  `trade_hs6` allows excluding them.
- Hong Kong re-exports mostly to mainland China. Both are in region `CHN`, so this double
  counting disappears in intra-regional trade.
- Quantities in BACI are partly converted from values or other units by CEPII; aggregate
  quantities can differ slightly between HS revisions.

### 1.6 What the data show

- **World polyethylene trade is 68–70 Mt a year** (2019–2024), roughly half of world
  production. 2023 by product: HDPE 25.2 Mt, LDPE/LLDPE 20.7 Mt, ethylene-alpha-olefin
  copolymers 15.5 Mt, EVA 3.2 Mt, other 3.2 Mt.
- **Largest importers 2023:** China 16.5 Mt, India 4.1, USA 3.4, Turkey 2.5, Vietnam 2.3.
  **Largest exporters:** USA 13.7 Mt, Saudi Arabia 9.9, Korea 4.4, Canada 3.8, UAE 3.5.
- **Russia:** exports fall from 1.34 Mt (2021) to 0.69 Mt (2023). Our partial Comtrade data
  had shown a drop to 0.2 Mt; that was mostly an artefact of missing partner reports, as
  suspected.
- **Check against our own reconciliation:** for the relations in both datasets, about half
  of our Comtrade-based quantities lie within ±10 % of BACI, the median absolute gap is
  6–11 %, and our totals are 2–13 % lower than BACI's. Example Saudi Arabia → Belgium 2024:
  Saudi Arabia reported 480 kt, Belgium 171 kt; we took Belgium's import report (171 kt),
  BACI's reconciled flow is 233 kt.
- From the phase-1 mirror analysis (17 reporters): only 21–30 % of relations agree within
  ±10 % between exporter and importer report, the CIF/FOB value ratio is 1.1–1.3, and
  11–37 % of the tonnage rests on weights estimated by Comtrade itself. Hubs such as Antwerp
  explain the largest gaps.

## 2. Regions

source: assumption. Ten regions plus rest of world (`ROW`), grouped by supply economics
and shipping geography. Representative ports are used for sea distances only.

Each region has **reporters** (~30 in total; they only matter for the Comtrade check, BACI
covers all countries) and **members** (all other
countries of the region, full lists in `config/regions.yaml`). Members are not queried, but
their trade is seen through the reporters' reports and must be counted in the right region.
Before this split, 37 % of inter-regional trade in 2023 fell into `ROW` (Spain, Austria,
Czechia, Oman, Colombia, ...), and trade such as Germany -> Spain looked like trade with the
rest of the world. With all countries mapped, `ROW` holds 0.4 % (mainly Australia and New
Zealand).

| Region | Reporters | Members (summary) | Port | Why |
|---|---|---|---|---|
| NAM North and Central America | USA, CAN, MEX | Central America, Caribbean | Houston | US Gulf Coast: largest export surplus thanks to cheap shale ethane |
| SAM South America | BRA, ARG, CHL | rest of South America | Santos | Braskem; net importing region |
| EUR Europe | DEU, BEL, NLD, FRA, ITA, GBR, POL, TUR | rest of EU, EFTA, Western Balkans, UKR, MDA | Rotterdam | Antwerp/Rotterdam hubs; Turkey as a large importer |
| CIS Russia and CIS | RUS | BLR, Central Asia, Caucasus | St. Petersburg | Sibur; reports no data since 2022, visible via mirror data only |
| MDE Middle East | SAU, ARE, QAT, IRN | KWT, OMN, BHR, IRQ, ISR, JOR, ... | Jebel Ali | Lowest-cost producers (cheap ethane); Iran reports irregularly |
| AFR Africa | EGY, ZAF | all other African countries | Durban | Importing region |
| IND India and South Asia | IND | PAK, BGD, LKA, NPL, ... | Nhava Sheva | Fast-growing demand |
| CHN China | CHN, HKG | MAC | Shanghai | Largest importer; Hong Kong mainly re-exports to China |
| NEA Northeast Asia | JPN, KOR, TWN | PRK, MNG | Busan | Korea a large exporter; Taiwan reported only as "Other Asia, nes" |
| SEA Southeast Asia | SGP, THA, MYS, VNM, IDN | PHL, MMR, KHM, LAO, BRN, TLS | Singapore | Singapore/Thailand export, Vietnam/Indonesia import |

Port limitations: one port per region is coarse. Russia ships PE to China largely by rail,
not via the Baltic; Africa is represented by Durban although Egypt and North Africa sit on
the Mediterranean.

## 3. Transport model

### 3.1 Formulation

A central planner supplies every region's demand at minimum total cost
(`src/ptf/model/transport.py`, solved with HiGHS):

    min  Σ_ij (prod_cost_i + freight_ij + tariff_ij) · x_ij  +  Σ_j penalty · u_j
    s.t. Σ_j x_ij        ≤ capacity_i     (capacity of each supplying region)
         Σ_i x_ij + u_j  ≥ demand_j       (demand of each region)
         x_ij ≥ 0,  u_j ≥ 0

- `x_ij` tonnes from region i to j; `x_ii` is local supply with zero freight
- `u_j` unmet demand, priced at `penalty_usd_t` (5,000 USD/t) so the LP stays solvable when
  a scenario removes capacity
- `demand_j = production_j + imports_j − exports_j` of the base year, where production is
  `capacity × utilisation` (assumption) and imports/exports are the observed flows **between**
  regions (trade within a region cancels out). Trade with `ROW` counts in imports/exports,
  but `ROW` itself is not part of the LP (no port, < 1 % of trade).
- `freight_ij = fixed + variable × distance_ij / 1000`, distances from searoute
- `tariff_ij = 0` in the base case (scenarios set it in USD/t)

### 3.2 Assumptions

All in `config/model.yaml`, each with a `source` field. Base year: **2023**.

| Region | Capacity (Mt) | Utilisation | Cash cost (USD/t) |
|---|---|---|---|
| NAM | 34 | 88 % | 650 |
| SAM | 5 | 80 % | 1,100 |
| EUR | 17 | 75 % | 1,200 |
| CIS | 5 | 85 % | 700 |
| MDE | 23 | 90 % | 500 |
| AFR | 3 | 75 % | 900 |
| IND | 7 | 88 % | 1,000 |
| CHN | 38 | 78 % | 1,000 |
| NEA | 10 | 80 % | 1,100 |
| SEA | 11 | 80 % | 1,050 |

- Capacities for NAM, MDE, EUR (Western Europe) and CHN are anchored on McKinsey's 2025
  figures (China 42, North America 34, Middle East 23, Western Europe 14 Mt; ~150 Mt
  worldwide); the others are orders of magnitude from public company information and still
  need individual checks.
- Utilisation around 80 % on average matches S&P Global's estimate of ~30 Mt of capacity
  above demand in 2024.
- **Cash costs are the least certain numbers.** They encode the ranking of the cost curve
  (cheap ethane in the Middle East and North America, expensive naphtha in Europe and Asia),
  not verified values.
- Freight: 40 USD/t fixed + 7 USD/t per 1,000 nm, derived from container rates of
  ~1,500–2,000 USD per 40ft box (~25 t) on Shanghai–Rotterdam before the Red Sea crisis.

### 3.3 Reading the duals

- **Price** (`price_usd_t`, dual of the demand constraint): extra total cost if region j needed
  one more tonne = marginal delivered cost = implied regional price. On every used route,
  `price_j = prod_cost_i + rent_i + freight_ij`: price differences between connected regions
  equal the freight, as spatial arbitrage requires.
- **Rent** (`rent_usd_t`, magnitude of the capacity dual): cost saving from one more tonne of
  capacity in region i. Positive only for regions running at full capacity: the margin of a
  low-cost producer over the marginal supplier. Regions with idle capacity have rent 0; the
  cheapest of them is the marginal supplier and sets the price level.
- Demand is fixed, so prices are purely cost-based. With ties between routes the duals are
  not unique.

The 3-region example in `tests/test_transport.py` derives flows, prices and rents by hand.

### 3.4 Results (2023, BACI data) and why model and reality differ

Full output: [model_results.md](model_results.md).

- Observed inter-regional trade is **44.1 Mt**; the model explains **42 %** of it on the same
  routes (Σ min(model, observed) / Σ observed), correlation 0.57. The model uses 8 routes,
  reality 90. With the partial Comtrade data it had been 40 % and 0.42.
- Demand (production assumption + net imports) totals 126 Mt; China 44.8 Mt, India 11.0 Mt.
- **Corner solution.** Global capacity (153 Mt) exceeds demand, so the LP shuts down the
  most expensive producers: Europe produces 0 t, Northeast Asia runs at 15 %, Southeast Asia
  at 87 %, all cheaper regions at 100 % of nameplate. North America ships 13.4 Mt to Europe
  (observed: 2.0 Mt), while the largest observed routes go to China (Middle East 6.2 Mt,
  North America 3.2, Southeast Asia 3.0, Northeast Asia 3.0).
- **Northeast Asia is the marginal supplier** (idle capacity at 1,100 USD/t), which puts all
  regional prices between 1,018 and 1,106 USD/t. Rents: Middle East 518, North America 376,
  Russia 353 USD/t.
- Why reality differs: long-term contracts and integrated downstream plants keep "expensive"
  crackers running; grades (LDPE/LLDPE/HDPE) are not interchangeable; buyers diversify
  suppliers for security; tariffs and trade policy (e.g. US–China) are not in the base case;
  a single cost per region hides the cost spread within a region; nameplate capacity is
  treated as fully usable.

### 3.5 Limitations and next steps

- Linear costs, fixed demand, one cost level per region, annual resolution.
- Possible calibration (SPEC phase 2b): a minimum utilisation per region (e.g. ≥ 60 %)
  to represent contracts and integration, a maximum utilisation below 100 % of nameplate,
  route-specific calibration markups, or an entropy/gravity model as benchmark.

## 4. Shipping monitor (IMF PortWatch)

### 4.1 Data

IMF PortWatch counts vessel transits through 28 maritime chokepoints per day and vessel
type (container, dry bulk, general cargo, RoRo, tanker), derived from satellite AIS
positions, from 2019-01-01 on. Access: ArcGIS REST API without a key, at most 1,000 rows
per request (paged with `resultOffset`). **Not real-time:** data arrive a few days late and
are published about weekly. Updates are incremental; the last `revision_days` (14) before the
latest stored day are fetched again because PortWatch revises recent days, and the clean
step keeps the latest download per day. Raw downloads are never overwritten.

AIS-based counts drop when ships switch off their transponders or when GPS jamming disturbs
positions. A collapse in counts therefore means "fewer ships visible", which is usually but
not always "fewer ships".

Since spec 003 the cleaning runs in dbt (`dbt/models/*/shipping`): the raw downloads are
read folder by folder and the most recently fetched value per day and location is kept with
a window function (`qualify row_number() ... = 1`); the app reads the marts.

### 4.2 Metrics (`src/ptf/shipping/metrics.py`, parameters in `config/shipping.yaml`)

- **7-day average** per chokepoint and vessel type: daily counts are noisy (weekdays,
  convoys).
- **Normal level:** for each day, the average daily traffic in the same ISO calendar week
  across the baseline years 2019–2023 (each year's weekly average first, then the mean over
  the years; the band in the chart is the lowest to highest year). Using the calendar week
  removes seasonality; 2019–2023 ends before the Red Sea attacks.
- **Deviation from normal** in % and a **disruption flag** when the 7-day average falls below
  70 % of normal. Chokepoints with less than 2 vessels a day of normal traffic are never
  flagged (Bering or Kerch Strait would otherwise flip to "-100 %" on a single quiet week).
- **Year-on-year:** against the same day 364 days earlier (same weekday).
- **Red Sea diversion ratio:** container ships at the Cape of Good Hope / (Cape +
  Bab el-Mandeb), 7-day basis.

### 4.3 What the data show (as of 2026-11-08)

- **Red Sea:** the Cape share of container ships was 22–27 % per year in 2019–2023 and
  75–78 % in 2024–2026. Container transits through Bab el-Mandeb fell from 6,739 (2023) to
  1,967 (2024), −71 %; at the Cape they tripled. There is no recovery in 2025–2026; in the
  latest week Bab el-Mandeb container traffic is 67 % below normal.
- **Strait of Hormuz:** total transits drop from ~78 a day (February 2026) to 3–13 a day from
  March 2026 on, tankers included; in the latest week tanker traffic is 98 % below normal.
  The cause is not analysed here (see the AIS caveat in 4.1). For polyethylene it matters
  directly: Middle East exports from the Gulf (e.g. Jubail, Jebel Ali) pass Hormuz.
- **Panama:** 12 % fewer transits in 2024 than in 2023 (drought restrictions).

### 4.4 Link to the transport model (next step)

The diversion ratio and the Hormuz figures are natural inputs for scenarios (SPEC section 5):
longer distances via the Cape for Asia–Europe trade, and reduced export capacity or a cost
markup for Gulf producers.

## 5. Dashboard data: ports, events, energy and freight

The app (`uv run python -m ptf.app`) started with the tabs Overview, Chokepoints
(section 4), Ports and Energy & freight; since spec 006 the buyer tabs Situation, Prices &
drivers and Sourcing (section 6) replace Overview and Energy & freight. All data are free and need no key; `ptf portwatch` and
`ptf market` (or the "Update data" button) refresh them.

### 5.1 Ports and disruption events (IMF PortWatch)

- **Port activity** (`Daily_Ports_Data`): port calls by vessel type and *estimated* import
  and export volumes (t/day) per port, derived by PortWatch from vessel draught and capacity
  (not customs statistics). Only the eleven ports in `config/shipping.yaml` are downloaded
  (Houston, Santos, Antwerp, Rotterdam, Jubail, Yanbu, Jebel Ali, Shanghai, Ningbo,
  Singapore, Busan): export hubs of the low-cost producers, the European polymer hubs and the
  large Asian import ports. Ports added later get their full history on the next update.
- The ports use **the same metrics as the chokepoints** (7-day average, normal = same
  calendar week 2019–2023, flag below 70 %); `ptf.shipping.metrics` works on generic
  "locations".
- **Disruption events** (`portwatch_disruptions_database`, ~130 events): cyclones,
  earthquakes, floods, droughts, wildfires and "other" events such as conflicts, with alert
  level and affected ports. The app shows open events and events ended in the last 30 days,
  orange and red alerts only.

FRED series are read from the newest CSV per series and joined with their metadata from
`config/markets.yaml` in dbt (`dbt/models/*/markets`); the GSCPI spreadsheet (old .xls)
is parsed by Python into a landing file first.

### 5.2 Energy, freight and supply-chain indicators

| Series | Source | Frequency | Why |
|---|---|---|---|
| Brent, WTI | FRED | daily | crude oil: feedstock cost of naphtha crackers, bunker fuel |
| Henry Hub (US gas) | FRED | daily | feedstock cost of US ethane crackers |
| Natural gas Europe, LNG Japan | FRED (IMF) | monthly | feedstock and energy cost in Europe and Asia |
| Gas spread Europe − US | computed (monthly means) | monthly | cost advantage of US producers |
| US PPI deep sea freight | FRED (BLS) | monthly | **proxy** for ocean freight rates |
| US PPI thermoplastic resins | FRED (BLS) | monthly | **proxy** for polymer price trends |
| CNY per USD, broad USD index | FRED | daily | competitiveness of Chinese and dollar-priced trade |
| GSCPI | New York Fed | monthly | global supply-chain stress, in standard deviations from the average |

- **Container freight rates** (Drewry WCI, Freightos FBX, SCFI) have no free downloadable
  history; the BLS producer price index for deep sea freight is the only free official
  series with a long history and is labelled as a proxy.
- Series with different units are compared **indexed to 100 at the start of the selected
  period**, never on a second y-axis.
- Two **key events** from `config/markets.yaml` (Red Sea attacks from 19 Nov 2023,
  Hormuz disruption from 1 Mar 2026) are drawn as dotted lines in all time series.

### 5.3 What the data show (as of early November 2026)

- **Oil and gas:** Brent rose from ~71 USD/bbl (February 2026) to up to 127 in March and
  135 in October 2026, and stood at 107 on 3 November. European gas and Japanese LNG are at
  ~25 USD/MMBtu (September), US Henry Hub at ~3: a spread of ~22 USD/MMBtu in favour of US
  producers.
- **Freight and supply chains:** the deep sea freight price index is 37 % above its level
  a year earlier; the GSCPI is +1.26 (October 2026), clearly above its long-run average of 0.
- **Gulf ports:** port calls at Jebel Ali are 78 % and at Jubail 67 % below normal, export
  volumes of Jubail 57 % below normal. **Yanbu**, Saudi Arabia's Red Sea port outside
  Hormuz, saw *more* calls from March to July 2026 (151–217 a month vs. ~90 before) – a
  plausible rerouting of Saudi exports – but almost none from August 2026 on. PortWatch
  reports zeros for these days (not missing rows); whether the port is idle or ships are not
  visible in the AIS data cannot be told from the data.
- PortWatch lists two open red-alert events: **HORMUZ-26** (since 1 Mar 2026) and **RED SEA
  TENSIONS** (since 16 Dec 2023).

### 5.4 Trade flows: port network and cargo types

- **Port network** (PortWatch `spillovers_port_level_impact`): directed links between ports
  with average transit days and the vessel capacity (deadweight tonnes) travelling on them per
  day. It is a **static snapshot** (last updated May 2025), covers **all vessel types
  together** and measures capacity, not the cargo actually carried. Only links with at least
  1,000 t/day are kept (8,084 of ~227,000, ~71 % of capacity).
- The largest links overall are short coastal and feeder services (Shanghai–Ningbo,
  Hong Kong–Shenzhen). The map therefore shows **long-haul links** by default: between
  different countries and at least 5 days of transit. Among the 100 largest of those, 18 start
  in **Port Hedland** (Australian iron ore to Chinese steel ports, 13–20 days); the largest
  outbound links of **Jubail** go to Singapore (15 days), Fujairah and Bahrain.
- **Cargo types** (PortWatch `Daily_Trade_Data_REG`): daily imports and exports per country
  by vessel type, where the vessel type stands for the cargo (tankers ~ oil, products,
  chemicals, LNG/LPG; dry bulk ~ ore, coal, grain; containers ~ manufactured goods including
  bagged polyethylene; RoRo ~ vehicles). The dataset has ~560,000 rows; the first download
  takes 20–25 minutes, so it is **switched off by default** (`download_country_trade`).
- Not freely available: port-to-port flows by cargo (e.g. crude oil tanker flows), which are
  the business of commercial providers such as Kpler or Vortexa.

## 6. Buyer view: situation, prices and sourcing exposure (spec 006)

The app is organised around the questions of a polyethylene buyer in Europe. The logic sits
in `src/ptf/insights/` (ADR-014); assumptions in `config/sourcing.yaml`.

### 6.1 Chokepoint exposure of imports

*Which share of Europe's imports from outside the region passes a chokepoint that is
disrupted right now?*

1. **Import sources:** `marts.mart_import_sources` (dbt) sums the BACI flows per year,
   importer region and exporter country; `share_extra` is the share in the importer region's
   imports from outside the region. Latest year: 2024.
2. **Routes:** the shortest sea route from each region's representative port to Rotterdam
   (`searoute`, `return_passages=True`), stored as `passages` in `sea_distances`. The mapping
   from searoute passages to PortWatch chokepoints is in `config/sourcing.yaml`.
3. **Disrupted today:** chokepoints whose 7-day mean of all vessels is below 70 % of the
   seasonal normal (section 4.2).
4. **Exposure** = tonnes from exporter countries whose route passes at least one disrupted
   chokepoint / all extra-regional tonnes.

**Result (BACI 2024, PortWatch to 8 Nov 2026):** Europe imported 6.9 Mt from outside the
region (63 % of European countries' imports come from within Europe). **52 %** of the
extra-European tonnes pass a disrupted chokepoint: the Middle East (Hormuz, Bab el-Mandeb,
Suez) and Asia (Bab el-Mandeb, Suez). The USA (37 %) ships across the open Atlantic.

**Limits:**
- One port per region: all Middle East exports are routed from Jebel Ali through Hormuz,
  although Saudi exports from Yanbu (Red Sea) and Israeli exports (Mediterranean) do not
  pass it; Egypt is routed from Durban. The exposure is an approximation.
- Trade data end in 2024; the routes are the normal routes, not today's diversions (ships
  going around the Cape are still counted as exposed – the point is the dependency).
- "Disrupted" is a traffic signal, not a closure: cargo may still arrive, but later and at
  higher freight cost.

### 6.2 Prices in EUR and feedstock vs. resin

USD prices and the US producer price indices are converted to EUR with FRED `DEXUSEU`
(US dollars per euro): daily prices with the rate of the same day (or the last earlier one),
monthly series with the monthly average rate. Example: Brent 80 USD at 1.10 USD/EUR =
72.73 EUR.

The chart "feedstock vs. resin" puts Brent, Henry Hub, European gas and two US resin price
indices on one axis (monthly averages, January 2019 = 100, log scale). If resin indices
rise more than feedstock, producer margins widen; a buyer can tell "the market went up"
from "the margin went up". There is no free polyethylene price series; the US PPIs for
thermoplastic resins and for plastics material and resin manufacturing are the proxies.

### 6.3 Traffic lights (`source: assumption`)

| Light | Measure | Amber from | Red from |
|---|---|---|---|
| Price | Brent in EUR, change over 90 days | +5 % | +10 % |
| Supply | chokepoint exposure (6.1) | 10 % | 25 % |
| Logistics | latest GSCPI (std. dev. from average) | 0.5 | 1.0 |

Higher is worse in all three cases. The thresholds are a starting point to be tuned; they
are not taken from a published benchmark. "What changed" lists chokepoints newly below
normal and new orange/red events within 7 days, and the three largest 30-day moves of the
market series.

### 6.4 Landed cost by supplier country (spec 007)

*What does one tonne cost delivered to Europe from each supplier country?*

landed = price + freight + duty (USD/t, converted to EUR with the latest `DEXUSEU`):

- **price:** BACI unit value of the country's exports to Europe (value / tonnes, FOB) in the
  latest year; optionally × (resin index latest / its average in that year) with the US PPI
  for plastics resins (`PCU325211325211`) – a proxy for "today", not a quote;
- **freight:** the transport model's assumption (40 USD/t + 7 USD/t per 1,000 nm,
  `config/model.yaml`) for the sea distance from the region's port to Rotterdam, × a freight
  factor (slider; Red Sea crisis rates were roughly 2–3× the pre-crisis level);
- **duty:** EU duty rate × (price + freight), because the EU customs value is CIF
  (insurance ignored). Rates in `config/sourcing.yaml`: 6.5 % third-country duty; 0 % for
  the USA (from 2026-07-01), South Korea, Egypt and Israel; 5.2 % for Mercosur (phase-in).
  Source: a TARIC mirror (tariffnumber.com), read 2026-11-13; to be checked in the official
  TARIC consultation before relying on it.

**Red Sea closed:** a second distance table with Suez, Bab el-Mandeb and Panama blocked
(`route_variants` in `config/model.yaml`). Panama has to be blocked as well, otherwise
searoute sends Asian cargo through Panama instead of around the Cape. Jebel Ali → Rotterdam
grows from 6,262 to 11,045 nm, Shanghai from 10,546 to 13,866 nm; Houston is unchanged.

**Result (BACI 2024 prices, 1.115 USD/EUR, freight factor 1):** cheapest delivered are
Uzbekistan (961 EUR/t), Iran (1,060), Qatar (1,144), the USA (1,201) and Saudi Arabia
(1,213); the average price within Europe is 1,355 EUR/t. Thanks to the duty preference the
USA lands close to the Gulf suppliers despite a higher FOB price. Closing the Red Sea adds
about 32 EUR/t for Middle East supplies (volume-weighted) at normal freight rates.

**Limits:**
- Unit values average all PE grades; differences between countries partly reflect the mix
  (e.g. more LLDPE or HDPE), not the price of the same grade.
- The model region Europe includes the UK, Turkey, Switzerland, Norway, Ukraine and others,
  where EU duties do not apply; most of Iran's volume goes to Turkey. GSP preferences (e.g.
  Uzbekistan) and anti-dumping or safeguard duties are not modelled.
- One port per region (section 6.1); no inland freight, insurance or port fees.


## 7. Breakdown by class (spec 008)

### 7.1 Commodity classes in world trade

`ptf clean` reads the whole BACI file (about 11 million flows per year) once and stores a
summary per year and HS4 heading (polyethylene per HS6 grade) in `landing_all_trade`
(about 250 KB). The dbt seed `commodity_classes` maps HS prefixes to classes (longest prefix
wins, everything else "Other goods"); `commodity_class_tree` holds the hierarchy all goods →
plastics in primary forms → polyethylene → grades. `marts.mart_trade_by_class` gives value,
tonnes and shares per year and leaf class.

| Class | HS | 2024: share of tonnes | share of value |
|---|---|---|---|
| Mineral fuels | 27 | 42.6 % | 13.2 % |
| Ores | 26 | 14.6 % | 1.6 % |
| Cereals and oilseeds | 10, 12 | 5.0 % | 1.3 % |
| Organic chemicals | 29 | 1.6 % | 2.1 % |
| Plastics in primary forms | 3901–3914 | 1.4 % | 1.5 % |
| of which polyethylene | 3901 | 0.5 % (70 Mt) | 0.4 % (86 bn USD) |
| Other goods | rest | 34.8 % | 80.4 % |

World trade 2024: 14.8 bn t, 22.9 trillion USD. **Limits:** BACI covers all transport modes
(sea, pipeline, road, rail, air), so these are shares of world trade, not of seaborne trade;
UNCTAD reports about 12 bn t loaded at sea. Flows without a quantity (about 1 % of value)
count with 0 t. The 2023 jump of "Other goods" tonnes comes from a few products with large
reported quantities and is not checked further.

### 7.2 Vessel classes at chokepoints

PortWatch counts transits per day in five classes (container, tanker, dry bulk, general
cargo, RoRo) and gives carrying capacity for container ships and tankers. The Chokepoints
tab shows the traffic mix in the baseline years vs. the last 90 days, the change per class
(7-day mean vs. the same calendar week in 2019–2023, the method of section 4.2 per class)
and the capacity mix of the last 12 months (container, tanker, other). Example Strait of
Hormuz 2025: tankers 70 % of capacity (822 of 1,175 million t).

### 7.3 Polyethylene grades

`marts.mart_import_sources_by_product` keeps the five HS6 grades. Sourcing and Landed cost
filter by grade; unit prices of one grade are comparable across countries, which removes
the product-mix effect of section 6.4 (the grades themselves are still broad: HS 390110
mixes LDPE and LLDPE).
