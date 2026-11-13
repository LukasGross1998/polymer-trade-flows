{{ config(enabled=var('country_trade_enabled')) }}
-- Optional: imports and exports per country by vessel type (download_country_trade).
select *
from {{ ref('stg_portwatch__country_trade') }}
order by iso3, date
