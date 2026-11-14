-- Daily marine weather per location; the most recent download wins per day (a later
-- download replaces an older forecast with a newer forecast or with the observed value).
select
    location_id,
    location_type,
    cast(date as date)               as date,
    cast(wave_height_m as double)    as wave_height_m,
    cast(wind_gusts_kmh as double)   as wind_gusts_kmh,
    cast(wind_speed_kmh as double)   as wind_speed_kmh,
    fetched_at
from {{ source('openmeteo', 'weather') }}
qualify row_number() over (partition by location_id, date order by fetched_at desc) = 1
