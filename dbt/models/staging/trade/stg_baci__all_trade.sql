-- World trade of all products per year and code (HS4, HS6 for polyethylene), base units.
select
    cast(year as integer)                          as year,
    cast(code as varchar)                          as code,
    cast(value_kusd as double) * 1000              as value_usd,
    cast(qty_t as double)                          as qty_t,
    cast(value_kusd_without_qty as double) * 1000  as value_usd_without_qty,
    cast(flows as bigint)                          as flows
from {{ source('baci', 'landing_all_trade') }}
