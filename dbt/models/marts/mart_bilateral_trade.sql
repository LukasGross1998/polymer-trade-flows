-- All polyethylene products summed per year, exporter and importer, with regions.
select
    f.year,
    f.exporter_iso3,
    f.importer_iso3,
    e.region                                            as exporter_region,
    i.region                                            as importer_region,
    sum(f.value_usd)                                    as value_usd,
    sum(f.qty_t)                                        as qty_t,
    sum(case when f.is_imputed then f.qty_t else 0 end) as imputed_qty_t
from {{ ref('fct_trade') }} as f
join {{ ref('dim_country') }} as e on f.exporter_iso3 = e.iso3
join {{ ref('dim_country') }} as i on f.importer_iso3 = i.iso3
group by all
