# Methodology

Model assumptions, data treatment and known limitations. Every number that is an assumption
lives in `config/` and is explained here. Generated figures and tables: [data_quality.md](data_quality.md).

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
exports (FOB) are grouped separately. Typical cause of an outlier: a wrong weight (unit error).

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

## 2. Regions

source: assumption. Ten regions plus rest of world (`ROW`), grouped by supply economics
and shipping geography. Representative ports are used for sea distances only.

| Region | Countries | Port | Why |
|---|---|---|---|
| NAM North America | USA, CAN, MEX | Houston | US Gulf Coast: largest export surplus thanks to cheap shale ethane |
| SAM South America | BRA, ARG, CHL | Santos | Braskem; net importing region |
| EUR Europe | DEU, BEL, NLD, FRA, ITA, GBR, POL, TUR | Rotterdam | Antwerp/Rotterdam hubs; Turkey as a large importer, logistically Mediterranean |
| CIS Russia | RUS | St. Petersburg | Sibur; reports no data since 2022, visible via mirror data only |
| MDE Middle East | SAU, ARE, QAT, IRN | Jebel Ali | Lowest-cost producers (cheap ethane); Iran reports irregularly |
| AFR Africa | EGY, ZAF | Durban | Importing region |
| IND India | IND | Nhava Sheva | Fast-growing demand, own market |
| CHN China | CHN, HKG | Shanghai | Largest importer; Hong Kong mainly re-exports to China |
| NEA Northeast Asia | JPN, KOR, TWN | Busan | Korea a large exporter; Taiwan reported only as "Other Asia, nes" |
| SEA Southeast Asia | SGP, THA, MYS, VNM, IDN | Singapore | Singapore/Thailand export, Vietnam/Indonesia import |

Port limitations: one port per region is coarse. Russia ships PE to China largely by rail,
not via the Baltic; Africa is represented by Durban although Egypt sits on the Mediterranean.
