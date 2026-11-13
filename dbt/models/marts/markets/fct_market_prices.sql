-- All configured market series in one long table: FRED series and the GSCPI.
select o.date, o.series_id, o.value
from (
    select date, series_id, value from {{ ref('stg_fred__series') }}
    union all
    select date, series_id, value from {{ ref('stg_gscpi') }}
) as o
join {{ ref('dim_market_series') }} using (series_id)
