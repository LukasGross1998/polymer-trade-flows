-- One row per year, exporter, importer and HS6 product (BACI, FOB values).
-- Missing quantities are imputed as value / median unit value of the same product and year
-- (unit values from flows with a reported quantity) and flagged.
with flows as (
    select
        t.year,
        e.iso3 as exporter_iso3,
        i.iso3 as importer_iso3,
        t.hs6,
        t.value_usd,
        t.qty_t
    from {{ ref('stg_baci__trade') }} as t
    join {{ ref('stg_baci__countries') }} as e on t.exporter_code = e.country_code
    join {{ ref('stg_baci__countries') }} as i on t.importer_code = i.country_code
),

with_unit_value as (
    select
        *,
        median(case when qty_t > 0 then value_usd / qty_t end)
            over (partition by year, hs6) as median_unit_value_usd_t
    from flows
)

select
    year,
    exporter_iso3,
    importer_iso3,
    hs6,
    value_usd,
    case
        when qty_t > 0 then qty_t
        when value_usd > 0 and median_unit_value_usd_t is not null
            then value_usd / median_unit_value_usd_t
    end as qty_t,
    not coalesce(qty_t > 0, false)
        and value_usd > 0
        and median_unit_value_usd_t is not null as is_imputed
from with_unit_value
