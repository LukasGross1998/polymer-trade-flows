-- Monthly EU27 imports of polyethylene from outside the EU per exporter country and grade
-- (Eurostat Comext, spec 019). unit_value_eur_t is CIF at the EU border: price plus sea
-- freight and insurance. Partner codes that are not countries (e.g. confidential trade)
-- have no ISO3 match and are left out.
with countries as (
    select iso2, max(iso3) as iso3
    from {{ ref('stg_baci__countries') }}
    where not is_historic and iso2 is not null
    group by iso2
)

select
    i.month,
    c.iso3                                   as exporter_iso3,
    d.country_name                           as exporter_name,
    d.region                                 as exporter_region,
    i.hs6,
    i.qty_t,
    i.value_eur,
    case when i.qty_t > 0 then i.value_eur / i.qty_t end as unit_value_eur_t
from {{ ref('stg_comext__imports') }} as i
inner join countries as c on i.partner_iso2 = c.iso2
inner join {{ ref('dim_country') }} as d on c.iso3 = d.iso3
