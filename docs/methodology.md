# Methodology

Model assumptions, data treatment and known limitations. Every number that is an assumption
lives in `config/` and is explained here. Generated figures and tables: [data_quality.md](data_quality.md). Every table and column:
[data_dictionary.md](data_dictionary.md).

## 1. Data & cleaning

### 1.1 Scope

| Item | Choice | Where |
|---|---|---|
| Product | HS 3901, polyethylene in primary forms (includes EVA 390130 and other ethylene polymers 390190) | `config/pipeline.yaml` |
| Years | 2019–2024, annual | `config/pipeline.yaml` |
| Reporters | ~30 largest PE traders, see section 2 | `config/regions.yaml` |
| Partners | all countries; unlisted ones map to `ROW` | `config/regions.yaml` |

HS 3901 as a whole is a known simplification: grades (LDPE, LLDPE, HDPE) and EVA have
different prices and trade patterns.

### 1.2 Sources

| Source | What | Access | Raw layer |
|---|---|---|---|
| UN Comtrade | annual bilateral imports and exports, net weight (kg) and value (USD) | public preview API, no key (ADR-003) | `data/raw/comtrade/{ISO3}_{year}.parquet`, records unchanged + `fetched_at` |
| UN Comtrade reference | area codes -> ISO3 | `files/v1/app/reference/*.json` | `data/raw/comtrade_reference/` |
| searoute | sea distance between representative ports | Python package, offline | `data/raw/distances/` |
| FRED `DCOILBRENTEU` | Brent spot price, daily, USD/bbl | CSV download, no key (ADR-004) | `data/raw/brent/DCOILBRENTEU.csv` |

Raw files are never overwritten. A cached Comtrade file is not fetched again; to pick up a
late-reporting country, delete its file and rerun `ingest`.

### 1.3 raw -> clean

`trade_reports` (one row per report, schema in SPEC section 3):

- keep flows `M` (import) and `X` (export); re-exports/re-imports are excluded
- keep totals only (`partner2Code=0`, `customsCode=C00`, `motCode=0`)
- drop the partner "World" and other aggregate areas
- numeric area codes -> ISO3 via the Comtrade reference table; "Other Asia, nes" (`S19`) is
  Comtrade's convention for **Taiwan** and is mapped to `TWN`
- net weight kg -> tonnes; a weight of 0 or missing becomes NaN ("unknown", not "zero")
- `qty_estimated_by_source` keeps Comtrade's own flag `isNetWgtEstimated`: Comtrade
  already fills missing weights itself, and we do not want to hide that

### 1.4 Quality rules

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

**Rule 5 – report.** `uv run python -m ptf.pipeline report` writes
[data_quality.md](data_quality.md) and `docs/figures/dq_*.png`: coverage per reporter and
year, mirror gaps, source of the agreed quantity, outliers and an inter-regional trade matrix.

### 1.5 Known limitations

- Only relations where at least one of the ~30 reporters is involved are covered. Trade
  between two `ROW` countries (e.g. Nigeria–Ghana) is missing. For the inter-regional model
  this matters little, because the large flows involve at least one listed country.
- Russia stopped reporting in 2022, Iran reports irregularly, and Taiwan does not report to
  Comtrade at all. Their trade is visible only through their partners' reports.
- Hong Kong re-exports mostly to mainland China. Both are in region `CHN`, so the double
  counting disappears in intra-regional trade; HK's own re-exports (flow `RX`) are excluded.
- Annual data mixes timing effects at year boundaries into the mirror gaps.

### 1.6 First observations (partial data, 2026-11-12)

Based on 17 of 30 reporters (Americas, Europe, Russia, Saudi Arabia, UAE, partly Qatar);
all of Asia and Africa are still missing because of the API quota. To be revisited once the
download is complete.

- **Mirror gaps are large.** Of the relations reported by both sides, only 21–30 % agree
  within ±10 % in quantity, and the median absolute gap is 26–40 %. The CIF/FOB value ratio
  has a median of 1.1–1.3, i.e. the value difference expected from freight and insurance.
- **Hub effects dominate the largest gaps.** Saudi Arabia reports 480 kt of exports to
  Belgium in 2024, Belgium records only 171 kt from Saudi Arabia. Goods shipped to Antwerp
  are often declared for customs in another EU country (the "Rotterdam/Antwerp effect").
- **Comtrade estimates a lot itself.** 11–37 % of the agreed tonnage per year rests on weights
  that Comtrade flags as estimated (`qty_estimated_by_source`).
- **A missing reporter is not a missing flow.** Russia stopped reporting after 2021. With the
  reporters loaded so far, its visible exports fall from 1.3 Mt (2021) to 0.2 Mt (2022):
  largely an artefact, because its main buyer China is not downloaded yet. Mirror data can
  only show what the loaded partners report.
- **US exports to China tripled** from 0.8 Mt (2019) to 2.7 Mt (2023) as new shale-based
  capacity on the Gulf Coast came online; the US is by far the largest net exporter.

## 2. Regions

source: assumption. Ten regions plus rest of world (`ROW`), grouped by supply economics
and shipping geography. Representative ports are used for sea distances only.

Each region has **reporters** (queried from Comtrade, ~30 in total) and **members** (all other
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

### 3.4 First results (2023, partial data) and why model and reality differ

Full output: [model_results.md](model_results.md).

- The model explains **40 %** of observed inter-regional tonnage on the same routes
  (Σ min(model, observed) / Σ observed); correlation 0.42. The model uses 9 routes, reality 59.
- **Corner solution.** Global capacity (153 Mt) exceeds demand (126 Mt), so the LP shuts
  down the most expensive producers completely: Europe produces 0 t, Northeast Asia runs at
  4 %, while all cheaper regions run at 100 % of nameplate. North America then ships 12.8 Mt
  to Europe (observed: 2.0 Mt).
- **Northeast Asia is the marginal supplier** (idle capacity at 1,100 USD/t), which puts all
  regional prices between 1,018 and 1,106 USD/t. Rents: Middle East 518, North America 376,
  Russia 353 USD/t.
- Why reality differs: long-term contracts and integrated downstream plants keep "expensive"
  crackers running; grades (LDPE/LLDPE/HDPE) are not interchangeable; buyers diversify
  suppliers for security; tariffs and trade policy (e.g. US–China) are not in the base case;
  a single cost per region hides the cost spread within a region; nameplate capacity is
  treated as fully usable.
- Data caveat: Asian and African reporters are not downloaded yet, so imports into Asia and
  hence demand there are underestimated (China 5.5 Mt observed imports vs. ~13–14 Mt real).

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

### 4.2 Metrics (`src/ptf/monitor/metrics.py`, parameters in `config/monitor.yaml`)

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

The app (`uv run python -m ptf.app`) has four tabs: Overview, Chokepoints (section 4),
Ports and Energy & freight. All data are free and need no key; `pipeline portwatch` and
`pipeline market` (or the "Update data" button) refresh them.

### 5.1 Ports and disruption events (IMF PortWatch)

- **Port activity** (`Daily_Ports_Data`): port calls by vessel type and *estimated* import
  and export volumes (t/day) per port, derived by PortWatch from vessel draught and capacity
  (not customs statistics). Only the eleven ports in `config/monitor.yaml` are downloaded
  (Houston, Santos, Antwerp, Rotterdam, Jubail, Yanbu, Jebel Ali, Shanghai, Ningbo,
  Singapore, Busan): export hubs of the low-cost producers, the European polymer hubs and the
  large Asian import ports. Ports added later get their full history on the next update.
- The ports use **the same metrics as the chokepoints** (7-day average, normal = same
  calendar week 2019–2023, flag below 70 %); `ptf.monitor.metrics` works on generic
  "locations".
- **Disruption events** (`portwatch_disruptions_database`, ~130 events): cyclones,
  earthquakes, floods, droughts, wildfires and "other" events such as conflicts, with alert
  level and affected ports. The app shows open events and events ended in the last 30 days,
  orange and red alerts only.

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
- Two **key events** from `config/market_data.yaml` (Red Sea attacks from 19 Nov 2023,
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
