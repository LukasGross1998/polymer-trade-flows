-- EU third-country (MFN) duty per polyethylene grade from WITS (spec 009). `mfn_pct` is the
-- highest rate of the grade's tariff lines: the rate of ordinary pellets (see trade/duties.py).
select
    cast(hs6 as varchar)        as hs6,
    cast(year as integer)       as year,
    cast(max_pct as double)     as mfn_pct,
    cast(avg_pct as double)     as avg_pct,
    cast(min_pct as double)     as min_pct,
    cast(lines as integer)      as tariff_lines,
    'World Bank WITS (TRAINS), reporter EU, partner world' as source
from {{ source('wits', 'landing_eu_duty') }}
