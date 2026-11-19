-- Rhine water levels (PEGELONLINE, 15-minute values); the newest download wins per time.
select
    station,
    cast(timestamp as timestamptz)  as measured_at,
    cast(level_cm as double)        as level_cm
from {{ source('rhine', 'levels') }}
where station is not null
qualify row_number() over (partition by station, timestamp order by fetched_at desc) = 1
