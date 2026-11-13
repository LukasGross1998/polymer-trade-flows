-- BACI polyethylene flows: typed and in base units (USD, t). Missing quantities stay null.
select
    cast(year as integer)            as year,
    cast(exporter_code as integer)   as exporter_code,
    cast(importer_code as integer)   as importer_code,
    cast(hs6 as varchar)             as hs6,
    cast(value_kusd as double) * 1000 as value_usd,
    cast(qty_t as double)            as qty_t
from {{ source('baci', 'landing_hs3901') }}
