-- Dalian LLDPE main contract (spec 011): the daily closing price in CNY/t as a market series.
select
    'DCE_LLDPE'             as series_id,
    cast(date as date)      as date,
    cast(close as double)   as value
from {{ source('dce', 'landing_dce') }}
where close is not null
