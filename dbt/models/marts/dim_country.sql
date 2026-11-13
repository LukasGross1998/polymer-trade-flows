-- One row per country (ISO3). Countries not listed in config/regions.yaml belong to ROW.
select
    c.iso3,
    c.country_name,
    coalesce(r.region, 'ROW')         as region,
    coalesce(r.is_reporter, false)    as is_reporter
from {{ ref('stg_baci__countries') }} as c
left join {{ ref('stg_reference__country_region') }} as r using (iso3)
where not c.is_historic
