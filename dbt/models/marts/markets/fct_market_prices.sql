-- All configured market series in one long table: FRED series, the GSCPI, the DCE price and
-- the Eurostat price indices.
select o.date, o.series_id, o.value
from (
    select date, series_id, value from {{ ref('stg_fred__series') }}
    union all
    select date, series_id, value from {{ ref('stg_gscpi') }}
    union all
    select date, series_id, value from {{ ref('stg_dce__lldpe') }}
    union all
    select date, series_id, value from {{ ref('stg_eurostat__series') }}
) as o
join {{ ref('dim_market_series') }} using (series_id)
