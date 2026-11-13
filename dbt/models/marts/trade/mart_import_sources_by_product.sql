-- Imports per year, importer region, exporter country and HS6 grade (spec 008).
select
    f.year,
    i.region                       as importer_region,
    f.exporter_iso3,
    e.country_name                 as exporter_name,
    e.region                       as exporter_region,
    f.hs6,
    e.region = i.region            as is_intra_regional,
    sum(f.qty_t)                   as qty_t,
    sum(f.value_usd)               as value_usd
from {{ ref('fct_trade') }} as f
join {{ ref('dim_country') }} as e on f.exporter_iso3 = e.iso3
join {{ ref('dim_country') }} as i on f.importer_iso3 = i.iso3
group by all
