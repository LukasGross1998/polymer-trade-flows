-- Where each region's polyethylene imports come from: one row per year, importer region
-- and exporter country. `share_extra` is the share in the importer region's imports from
-- outside the region (trade within the region has no share), the base of the buyer view.
with by_exporter as (
    select
        year,
        importer_region,
        exporter_iso3,
        exporter_region,
        exporter_region = importer_region as is_intra_regional,
        sum(qty_t)                        as qty_t,
        sum(value_usd)                    as value_usd
    from {{ ref('mart_bilateral_trade') }}
    group by all
)

select
    b.year,
    b.importer_region,
    b.exporter_iso3,
    c.country_name as exporter_name,
    b.exporter_region,
    b.is_intra_regional,
    b.qty_t,
    b.value_usd,
    case
        when not b.is_intra_regional then
            b.qty_t / sum(case when not b.is_intra_regional then b.qty_t end)
                over (partition by b.year, b.importer_region)
    end as share_extra
from by_exporter as b
join {{ ref('dim_country') }} as c on b.exporter_iso3 = c.iso3
