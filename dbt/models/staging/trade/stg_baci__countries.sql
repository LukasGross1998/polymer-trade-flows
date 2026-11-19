-- BACI country list. Comtrade pseudo codes are mapped to real countries via the aliases
-- from config/regions.yaml (e.g. "S19" Other Asia, nes -> TWN).
select
    cast(c.country_code as integer)        as country_code,
    trim(c.country_name)                   as country_name,
    coalesce(a.iso3, trim(c.country_iso3)) as iso3,
    trim(c.country_iso2)                   as iso2,
    -- historic entries such as "Fed. Rep. of Germany (...1990)" end before our period
    trim(c.country_name) like '%(...%'     as is_historic
from {{ source('baci', 'landing_country_codes') }} as c
left join {{ source('reference', 'country_aliases') }} as a
    on trim(c.country_iso3) = a.code
