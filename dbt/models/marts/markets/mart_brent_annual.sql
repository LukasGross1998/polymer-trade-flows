-- Annual average Brent price and number of quoted days (for the model's cost assumptions).
select
    year(date)    as year,
    avg(value)    as brent_usd_per_bbl,
    count(*)      as quoted_days
from {{ ref('fct_market_prices') }}
where series_id = 'DCOILBRENTEU'
group by year(date)
order by year
