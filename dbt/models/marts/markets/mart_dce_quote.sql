-- Latest intraday quote of the Dalian LLDPE main contract (spec 012): at most one row.
select
    cast(symbol as varchar)                         as symbol,
    cast("last" as double)                          as last_cny_t,
    cast(bid as double)                             as bid_cny_t,
    cast(ask as double)                             as ask_cny_t,
    cast(prev_settle as double)                     as prev_settle_cny_t,
    cast(tick_time as varchar)                      as tick_time_beijing,
    cast(trading_day as date)                       as trading_day,
    cast(fetched_at as timestamp with time zone)    as fetched_at
from {{ source('dce', 'landing_dce_quote') }}
