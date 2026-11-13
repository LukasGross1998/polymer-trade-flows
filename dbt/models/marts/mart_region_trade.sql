-- Trade per year and region pair (including trade within a region): input of the LP.
select
    year,
    exporter_region,
    importer_region,
    sum(value_usd)     as value_usd,
    sum(qty_t)         as qty_t,
    sum(imputed_qty_t) as imputed_qty_t
from {{ ref('mart_bilateral_trade') }}
group by all
