{{ config(enabled=var('country_trade_enabled')) }}
-- Optional: daily imports and exports per country by vessel type.
select
    cast(date as date) as date,
    ISO3               as iso3,
    country,
    "import", "export",
    import_tanker, import_dry_bulk, import_container, import_general_cargo, import_roro,
    export_tanker, export_dry_bulk, export_container, export_general_cargo, export_roro,
    fetched_at
from {{ source('portwatch', 'country_trade_daily') }}
where ISO3 is not null
qualify row_number() over (partition by date, ISO3 order by fetched_at desc) = 1
