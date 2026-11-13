-- Market series with their metadata: the table the "Energy & freight" tab reads.
select f.date, f.series_id, d.name, d.unit, d.frequency, d."group", f.value
from {{ ref('fct_market_prices') }} as f
join {{ ref('dim_market_series') }} as d using (series_id)
order by f.series_id, f.date
