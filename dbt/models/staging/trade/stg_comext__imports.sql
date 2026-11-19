-- Eurostat Comext: EU27 imports from outside the EU per month, partner and PE grade (spec 019).
-- Values in EUR at the EU border (CIF), quantities converted from 100 kg to tonnes.
select
    cast(month as varchar)          as month,
    cast(partner_iso2 as varchar)   as partner_iso2,
    cast(hs6 as varchar)            as hs6,
    cast(value_eur as double)       as value_eur,
    cast(qty_100kg as double) / 10  as qty_t
from {{ source('comext', 'landing_eu_imports') }}
